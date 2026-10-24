#!/usr/bin/env python3
"""Small LAN-only DJW media server for the PC and DJW Server Edition TV app."""
import base64
import hashlib
import hmac
import html
import ipaddress
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import ssl
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CONFIG = Path('/etc/djw-nas/server.json')
MAX_ITEMS = 12000
AUDIO = {'.mp3', '.m4a', '.aac', '.flac', '.wav', '.ogg', '.opus', '.wma', '.aif', '.aiff'}
VIDEO = {'.mp4', '.mkv', '.avi', '.mov', '.m4v', '.webm', '.ts', '.mpg', '.mpeg', '.wmv'}
ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,48}$')


def load_config():
    return json.loads(CONFIG.read_text())


def private_address(value):
    try:
        ip = ipaddress.ip_address(value)
        return ip.is_private or ip.is_loopback
    except ValueError:
        return False


class Store:
    def __init__(self):
        self.config = load_config()
        self.tokens_file = Path(self.config['tokens_file'])
        self.lock = threading.RLock()
        self.failures = {}
        self.tokens = {}
        if self.tokens_file.exists():
            try:
                self.tokens = json.loads(self.tokens_file.read_text())
            except (OSError, json.JSONDecodeError):
                self.tokens = {}

    def admin_password_ok(self, value):
        try:
            salt, digest = self.config['admin_password_hash'].split(':', 1)
            candidate = hashlib.pbkdf2_hmac('sha256', value.encode(), bytes.fromhex(salt), 260000).hex()
            return hmac.compare_digest(candidate, digest)
        except (ValueError, KeyError):
            return False

    def allow_pair(self, address, code):
        with self.lock:
            now = time.monotonic()
            recent = [x for x in self.failures.get(address, []) if now - x < 300]
            if len(recent) >= 6:
                return None
            if not hmac.compare_digest(str(code), str(self.config.get('tv_pin', ''))):
                recent.append(now)
                self.failures[address] = recent
                return False
            self.failures.pop(address, None)
            token = secrets.token_urlsafe(32)
            digest = hashlib.sha256(token.encode()).hexdigest()
            self.tokens[digest] = int(time.time())
            self.tokens_file.parent.mkdir(parents=True, exist_ok=True)
            temp = self.tokens_file.with_suffix('.tmp')
            temp.write_text(json.dumps(self.tokens))
            os.chmod(temp, 0o600)
            temp.replace(self.tokens_file)
            return token

    def token_ok(self, value):
        if not value:
            return False
        digest = hashlib.sha256(value.encode()).hexdigest()
        with self.lock:
            return digest in self.tokens

    def sources(self, kind=None):
        result = []
        for item in self.config.get('sources', []):
            if kind and item['kind'] != kind:
                continue
            if ID_RE.fullmatch(item['id']) and Path(item['path']).is_dir():
                result.append(item)
        return result

    def resolve(self, source_id, rel=''):
        for source in self.sources():
            if source['id'] != source_id:
                continue
            root = Path(source['path']).resolve()
            candidate = (root / rel).resolve(strict=True)
            if candidate != root and not candidate.is_relative_to(root):
                raise FileNotFoundError
            return source, candidate
        raise FileNotFoundError

    def media_items(self, kind=None, host='localhost:8787', scheme='https'):
        out = []
        for source in self.sources(kind):
            allowed = AUDIO if source['kind'] == 'Music' else VIDEO
            root = Path(source['path']).resolve()
            try:
                for folder, dirs, names in os.walk(root, followlinks=False):
                    dirs[:] = sorted([d for d in dirs if not d.startswith('.') and not Path(folder, d).is_symlink()], key=str.casefold)
                    for name in sorted(names, key=str.casefold):
                        path = Path(folder, name)
                        if path.suffix.lower() not in allowed or path.is_symlink():
                            continue
                        try:
                            resolved = path.resolve(strict=True)
                            if not resolved.is_relative_to(root) or not resolved.is_file():
                                continue
                            rel = resolved.relative_to(root).as_posix()
                        except (OSError, RuntimeError):
                            continue
                        quoted = urllib.parse.quote(rel, safe='/')
                        url = f'{scheme}://{host}/media/{source["id"]}/{quoted}'
                        title = path.stem
                        mime = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
                        # Aliases cover the common DJW client naming conventions.
                        out.append({'id':f'{source["id"]}:{rel}', 'title':title, 'name':title,
                                    'fileName':path.name, 'kind':source['kind'], 'type':source['kind'],
                                    'category':source['kind'], 'source':source['id'], 'url':url,
                                    'mediaUrl':url, 'playUrl':url, 'mime':mime, 'mimeType':mime,
                                    'artUrl':'', 'posterUrl':'', 'album':path.parent.name,
                                    'artist':'', 'duration':0})
                        except OSError:
                            continue
                        if len(out) >= MAX_ITEMS:
                            return out
            except OSError:
                continue
        return out


STORE = Store()


class Handler(BaseHTTPRequestHandler):
    server_version = 'DJW-Main/1.0'
    sys_version = ''

    def log_message(self, fmt, *args):
        # Do not write bearer tokens or query strings into system logs.
        route = urllib.parse.urlsplit(self.path).path
        print(f'[{self.log_date_time_string()}] {self.client_address[0]} {self.command} {route}', flush=True)

    def send_json(self, status, payload, headers=None):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != 'HEAD':
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def send_text(self, status, text, content_type='text/plain; charset=utf-8', headers=None):
        body = text.encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def admin_ok(self):
        value = self.headers.get('Authorization', '')
        if not value.startswith('Basic '):
            return False
        try:
            user, password = base64.b64decode(value[6:], validate=True).decode().split(':', 1)
            return hmac.compare_digest(user, 'admin') and STORE.admin_password_ok(password)
        except (ValueError, UnicodeError):
            return False

    def token_value(self, query):
        auth = self.headers.get('Authorization', '')
        bearer = auth[7:] if auth.startswith('Bearer ') else ''
        return query.get('token', [''])[0] or self.headers.get('X-DJW-Token', '') or bearer

    def authorized(self, query):
        return (self.client_address[0] in ('127.0.0.1', '::1') or self.admin_ok() or
                STORE.token_ok(self.token_value(query)))

    def do_POST(self):
        if not private_address(self.client_address[0]):
            return self.send_json(403, {'error':'LAN only'})
        route = urllib.parse.urlsplit(self.path).path
        if route == '/pair':
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 4096:
                    return self.send_json(413, {'error':'Invalid request size'})
                data = json.loads(self.rfile.read(length))
                pin = data.get('pin', data.get('code', data.get('pairingCode', '')))
            except (ValueError, json.JSONDecodeError):
                return self.send_json(400, {'error':'Invalid pairing request'})
            token = STORE.allow_pair(self.client_address[0], pin)
            if token is None:
                return self.send_json(429, {'error':'Too many pairing attempts'})
            if token is False:
                return self.send_json(401, {'error':'Incorrect pairing code'})
            return self.send_json(200, {'token':token, 'serverToken':token, 'accessToken':token,
                                        'ready':True, 'paired':True, 'name':'DJW Main Unit', 'version':'1.0'})
        if route in ('/control', '/disconnect'):
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            if not self.authorized(query):
                return self.send_json(401, {'error':'Unauthorized'})
            return self.send_json(200, {'ok':True, 'success':True})
        return self.send_json(404, {'error':'Not found'})

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not private_address(self.client_address[0]):
            return self.send_json(403, {'error':'LAN only'})
        parsed = urllib.parse.urlsplit(self.path)
        route = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        if route == '/api/health':
            return self.send_json(200, {'ok':True, 'service':'DJW Main Unit', 'version':'1.0'})
        if route in ('/status', '/api/status'):
            return self.send_json(200, {'ok':True, 'paired':True, 'server':'DJW Main Unit'})
        if route == '/kiosk':
            if self.client_address[0] not in ('127.0.0.1', '::1'):
                return self.send_json(404, {'error':'Not found'})
            try:
                body = (Path('/opt/djw-nas/app/kiosk.html')).read_bytes()
            except OSError:
                return self.send_json(500, {'error':'Player UI is missing'})
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Content-Security-Policy', "default-src 'self'; media-src 'self' blob:; img-src 'self' data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'")
            self.end_headers()
            if self.command != 'HEAD': self.wfile.write(body)
            return
        if route == '/':
            if not self.admin_ok():
                return self.send_text(401, 'DJW Main Unit administration', headers={'WWW-Authenticate':'Basic realm="DJW Main Unit"'})
            return self.send_json(200, {'name':'DJW Main Unit', 'version':'1.0', 'status':'online', 'pin':STORE.config['tv_pin']})
        if route in ('/library', '/djw/library', '/api/library'):
            if not self.authorized(query):
                return self.send_json(401, {'error':'Unauthorized'})
            kind = query.get('kind', [None])[0]
            kind = {'Film':'Film','Films':'Film','TV':'TV','Music':'Music'}.get(kind, kind)
            if kind not in (None, 'Music', 'Film', 'TV'):
                return self.send_json(400, {'error':'Invalid media kind'})
            host = self.headers.get('Host', 'localhost:8787')
            items = STORE.media_items(kind, host=host)
            return self.send_json(200, {'items':items, 'media':items, 'library':items,
                                        'results':items, 'total':len(items), 'server':'DJW Main Unit', 'version':'1.0'})
        if route in ('/media', '/file', '/art') or route.startswith('/media/'):
            if not self.authorized(query):
                return self.send_json(401, {'error':'Unauthorized'})
            if route == '/art':
                return self.send_json(404, {'error':'Artwork not found'})
            if route == '/file':
                ident = query.get('id', [''])[0]
                source_id, sep, rel = ident.partition(':')
                if not sep:
                    return self.send_json(404, {'error':'File not found'})
            elif route == '/media':
                source_id = query.get('source', [''])[0]
                rel = query.get('path', [''])[0]
            else:
                bits = route.split('/', 3)
                if len(bits) != 4:
                    return self.send_json(404, {'error':'File not found'})
                source_id, rel = bits[2], urllib.parse.unquote(bits[3])
            try:
                source, path = STORE.resolve(source_id, rel)
                allowed = AUDIO if source['kind'] == 'Music' else VIDEO
                if not path.is_file() or path.suffix.lower() not in allowed:
                    raise FileNotFoundError
                return self.send_file(path)
            except (OSError, ValueError, RuntimeError):
                return self.send_json(404, {'error':'Media file not found or source offline'})
        return self.send_json(404, {'error':'Not found'})

    def send_file(self, path):
        size = path.stat().st_size
        start, end, partial = 0, size - 1, False
        raw = self.headers.get('Range', '')
        if raw:
            match = re.fullmatch(r'bytes=(\d*)-(\d*)', raw.strip())
            if not match or (not match.group(1) and not match.group(2)):
                return self.invalid_range(size)
            if match.group(1):
                start = int(match.group(1)); end = int(match.group(2)) if match.group(2) else size - 1
            else:
                suffix = int(match.group(2))
                if suffix == 0: return self.invalid_range(size)
                start = max(0, size - suffix)
            if start >= size or start > end: return self.invalid_range(size)
            end = min(end, size - 1); partial = True
        length = max(0, end - start + 1)
        self.send_response(206 if partial else 200)
        self.send_header('Content-Type', mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(length))
        if partial: self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        if self.command == 'HEAD': return
        try:
            with path.open('rb') as stream:
                stream.seek(start); left = length
                while left:
                    chunk = stream.read(min(left, 512 * 1024))
                    if not chunk: break
                    self.wfile.write(chunk); left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def invalid_range(self, size):
        self.send_response(416)
        self.send_header('Content-Range', f'bytes */{size}')
        self.send_header('Content-Length', '0')
        self.end_headers()


def main():
    server = ThreadingHTTPServer(('0.0.0.0', 8787), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    config = load_config()
    context.load_cert_chain(config['tls_cert'], config['tls_key'])
    server.socket = context.wrap_socket(server.socket, server_side=True)
    print('DJW Main Unit serving HTTPS on port 8787', flush=True)
    server.serve_forever(poll_interval=0.5)


if __name__ == '__main__':
    main()
