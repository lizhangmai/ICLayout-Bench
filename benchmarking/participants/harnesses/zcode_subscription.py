"""ZCode's managed OAuth store and its native encrypted credential format."""

import json
import os
import shutil
import subprocess
from pathlib import Path

from benchmarking.files import write_json
from benchmarking.participants.harnesses.credentials import credential_values

PROVIDERS = {
    'account:bigmodel-individual-coding-plan': ('bigmodel', 'https://open.bigmodel.cn/api/anthropic'),
    'account:zai-individual-coding-plan': ('zai', 'https://api.z.ai/api/anthropic'),
}

# ZCode 0.17's AES-256-GCM store uses Node's OS identity unless an explicit
# credential secret is supplied. Decode with the CLI's existing Node runtime;
# credential values travel through captured stdin/stdout, never argv or logs.
READ_CREDENTIALS = r'''
const fs = require('node:fs');
const os = require('node:os');
const crypto = require('node:crypto');
try {
  const input = JSON.parse(fs.readFileSync(0, 'utf8'));
  let username = 'unknown';
  try { username = os.userInfo().username; } catch {}
  const secret = input.secret || `zcode-credential-fallback:${os.platform()}:${input.home}:${username}`;
  const key = crypto.createHash('sha256').update(secret).digest();
  const raw = JSON.parse(fs.readFileSync(input.path, 'utf8'));
  if (!raw || Array.isArray(raw) || typeof raw !== 'object') throw Error();
  const values = {};
  for (const [name, value] of Object.entries(raw)) {
    if (typeof value !== 'string') throw Error();
    if (!value.startsWith('enc:v1:')) { values[name] = value; continue; }
    const parts = value.slice(7).split('.');
    if (parts.length !== 3) throw Error();
    const [iv, tag, data] = parts.map(value => Buffer.from(value, 'base64url'));
    if (iv.length !== 12 || tag.length !== 16) throw Error();
    const cipher = crypto.createDecipheriv('aes-256-gcm', key, iv);
    cipher.setAuthTag(tag);
    values[name] = Buffer.concat([cipher.update(data), cipher.final()]).toString('utf8');
  }
  process.stdout.write(JSON.stringify({cipher_secret: secret, credentials: values}));
} catch {
  process.stderr.write('ZCode OAuth credential store cannot be decoded');
  process.exitCode = 1;
}
'''


def read_credentials(directory, *, env=None, secret=None):
    path = Path(directory) / 'credentials.json'
    if not path.is_file() or path.is_symlink() or path.resolve() != path:
        raise ValueError('ZCode OAuth credentials must be a regular file in the selected profile')
    node = shutil.which('node')
    if node is None:
        raise ValueError('ZCode OAuth encrypted credentials require Node.js on PATH')
    env = os.environ if env is None else env
    request = {'path': str(path), 'home': env.get('HOME') or str(Path.home()),
               'secret': secret if secret is not None else env.get('ZCODE_CREDENTIAL_SECRET', '').strip()}
    result = subprocess.run([node, '-e', READ_CREDENTIALS], input=json.dumps(request),
                            capture_output=True, text=True, timeout=10, check=False)
    if result.returncode:
        raise ValueError('ZCode OAuth credential store cannot be decoded with the selected cipher context')
    return json.loads(result.stdout)


def validate_account(values, provider, family, identity=None):
    current = values.get(f'account-provider:{provider}:identity')
    if (not current or (identity is not None and current != identity)
            or values.get(f'account-provider:{provider}:auth-source') != 'oauth'
            or not values.get(f'oauth:{family}:access_token') or not values.get('zcodejwttoken')):
        raise ValueError('ZCode subscription account changed or requires native OAuth login')
    return current


def resolve(home, provider, kind, options, env):
    if provider not in PROVIDERS:
        raise ValueError('ZCode subscription requires an individual Coding Plan account provider')
    family, endpoint = PROVIDERS[provider]
    if kind != 'anthropic' or options != {'baseURL': endpoint}:
        raise ValueError('ZCode subscription accepts its official endpoint without API key overrides')
    directory = home.resolve() / '.zcode/v2'
    decoded = read_credentials(directory, env=env)
    identity = validate_account(decoded['credentials'], provider, family)
    auth = {'credential_home': str(directory), 'provider': provider, 'family': family,
            'account_identity': identity, 'cipher_secret': decoded['cipher_secret']}
    return auth, decoded['credentials']


def prepare(private, auth, env):
    directory = Path(auth['credential_home'])
    decoded = read_credentials(directory, secret=auth['cipher_secret'])
    validate_account(decoded['credentials'], auth['provider'], auth['family'], auth['account_identity'])
    record = private / 'zcode-subscription.json'
    if record.exists() and json.loads(record.read_text()) != auth:
        raise ValueError('ZCode subscription account or credential source changed during continuation')
    target = private / 'native-home/.zcode/v2'
    if target.is_symlink():
        if target.resolve() != directory:
            raise ValueError('ZCode subscription credential storage changed during continuation')
    elif target.exists():
        raise ValueError('ZCode subscription credentials require the managed native directory')
    else:
        target.symlink_to(directory, target_is_directory=True)
    directory.chmod(0o700)
    (directory / 'credentials.json').chmod(0o600)
    write_json(record, auth)
    # HOME isolates CLI runtime settings and sessions. Preserve the login's
    # cipher context so the native store remains readable after that isolation.
    env['ZCODE_CREDENTIAL_SECRET'] = auth['cipher_secret']


def redactions(output):
    record = Path(output) / '.private/zcode-subscription.json'
    if not record.exists():
        return set()
    auth = json.loads(record.read_text())
    decoded = read_credentials(Path(auth['credential_home']), secret=auth['cipher_secret'])
    return credential_values(decoded['credentials']) | {auth['cipher_secret']}
