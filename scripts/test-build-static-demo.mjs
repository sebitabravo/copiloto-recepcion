import test from 'node:test';
import assert from 'node:assert/strict';
import {copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync,
  symlinkSync, writeFileSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';

const root = fileURLToPath(new URL('..', import.meta.url));
function fixture(t) {
  const work = mkdtempSync(join(tmpdir(), 'static-demo-build-'));
  t.after(() => rmSync(work, {recursive: true, force: true}));
  const repo = join(work, 'repo');
  mkdirSync(join(repo, 'scripts'), {recursive: true});
  mkdirSync(join(repo, 'landing', 'fonts'), {recursive: true});
  copyFileSync(join(root, 'scripts/build-static-demo.sh'), join(repo, 'scripts/build-static-demo.sh'));
  copyFileSync(join(root, 'scripts/write-static-config.py'), join(repo, 'scripts/write-static-config.py'));
  // Solo assets públicos: nunca se abre el config.js local ni se copia el árbol de trabajo completo.
  for (const name of readdirSync(join(root, 'landing'))) {
    if (/\.(html|css|js|svg|png|txt|xml)$/.test(name) && name !== 'config.js') {
      copyFileSync(join(root, 'landing', name), join(repo, 'landing', name));
    }
  }
  writeFileSync(join(repo, 'landing/config.js'), 'window.COPILOTO_CONFIG = {websiteToken: "fixture-token"};\n');
  const build = out => spawnSync('bash', ['scripts/build-static-demo.sh'], {cwd: repo, encoding: 'utf8',
    env: {...process.env, PUBLIC_SITE_URL: 'https://example.test', STATIC_DEMO_OUT: out ?? ''}});
  return {work, repo, build};
}

function successful(result) {
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.equal(result.stderr, '');
  assert.match(result.stdout, /^Listo: dist\/ con \d+ archivos · URL pública: https:\/\/example.test\n/);
}

test('dangerous output targets are rejected without touching sentinels or source', async t => {
  for (const kind of ['repository', 'source', 'source-child', 'ancestor', 'unmanaged']) {
    await t.test(kind, t => {
      const {work, repo, build} = fixture(t);
      const out = {repository: repo, source: join(repo, 'landing'),
        'source-child': join(repo, 'landing', 'nested'), ancestor: work,
        unmanaged: join(work, 'important')}[kind];
      mkdirSync(out, {recursive: true});
      const sentinel = join(out, 'KEEP.txt');
      writeFileSync(sentinel, 'sentinel');
      const source = readFileSync(join(repo, 'landing/demo.html'), 'utf8');
      const result = build(out);
      assert.equal(result.status, 2, result.stdout + result.stderr);
      assert.equal(result.stdout, '');
      assert.equal(result.stderr, 'Error: STATIC_DEMO_OUT debe ser dist/ o una salida externa vacía o creada por este script.\n');
      assert.equal(readFileSync(sentinel, 'utf8'), 'sentinel');
      assert.equal(readFileSync(join(repo, 'landing/demo.html'), 'utf8'), source);
    });
  }
});

test('a symlink output cannot redirect cleanup to another directory', {skip: process.platform === 'win32'}, t => {
  const {work, build} = fixture(t);
  const target = join(work, 'important');
  mkdirSync(target);
  writeFileSync(join(target, 'KEEP.txt'), 'sentinel');
  const out = join(work, 'alias');
  symlinkSync(target, out, 'dir');
  const result = build(out);
  assert.equal(result.status, 2);
  assert.equal(result.stdout, '');
  assert.equal(result.stderr, 'Error: STATIC_DEMO_OUT debe ser dist/ o una salida externa vacía o creada por este script.\n');
  assert.equal(readFileSync(join(target, 'KEEP.txt'), 'utf8'), 'sentinel');
});

test('default dist builds and rebuilds, substitutes public URLs and never publishes local config', t => {
  const {repo, build} = fixture(t);
  successful(build());
  const out = join(repo, 'dist');
  writeFileSync(join(out, 'obsolete.txt'), 'old build');
  successful(build());
  assert.equal(existsSync(join(out, 'obsolete.txt')), false);
  for (const name of readdirSync(out).filter(name => /\.(html|txt|xml)$/.test(name))) {
    assert.doesNotMatch(readFileSync(join(out, name), 'utf8'), /__PUBLIC_SITE_URL__/, name);
  }
  const config = readFileSync(join(out, 'config.js'), 'utf8');
  assert.doesNotMatch(config, /fixture-token|https?:\/\/|localhost/);
  assert.match(config, /staticDemo: true/);
  const demo = readFileSync(join(out, 'demo.html'), 'utf8');
  const shimTag = demo.indexOf('src="static-demo.js"');
  assert.ok(shimTag > -1 && shimTag < demo.indexOf('src="demo-shared.js'));
  assert.equal(readFileSync(join(out, 'demo/index.html'), 'utf8'), demo);
});

test('external empty and new outputs rebuild safely without touching neighboring files', t => {
  const {work, build} = fixture(t);
  const out = join(work, 'output');
  writeFileSync(join(work, 'KEEP.txt'), 'sentinel');
  successful(build(out));
  writeFileSync(join(out, 'obsolete.txt'), 'old build');
  successful(build(out));
  assert.equal(existsSync(join(out, 'obsolete.txt')), false);
  assert.equal(readFileSync(join(work, 'KEEP.txt'), 'utf8'), 'sentinel');
  const empty = join(work, 'empty');
  mkdirSync(empty);
  successful(build(empty));
});

test('local demo permissions acceptance is isolated and installs nothing', () => {
  const result = spawnSync('python', [join(root, 'scripts/check_demo_local.py'), '--permissions-only'],
    {cwd: root, encoding: 'utf8', timeout: 180000});
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.equal(result.stderr, '');
  assert.match(result.stdout, /2\/2 comprobaciones de permisos pasan/);
  if (process.platform === 'win32') {
    assert.match(result.stdout, /ACL NTFS inicial: acceso amplio heredado y explícito confirmado/);
    assert.match(result.stdout, /principales=current-user\/SYSTEM\/Administrators, acceso amplio=0/);
    assert.match(result.stdout, /PASA fallo previo a servicios: PowerShell ausente\/error ACL/);
  }
});



test('el build decide la IA y la voz por las claves del entorno', t => {
  const {build, work, repo} = fixture(t);
  const plain = join(work, 'sin-claves');
  successful(build(plain));
  assert.match(readFileSync(join(plain, 'config.js'), 'utf8'), /aiChat: false/);
  assert.match(readFileSync(join(plain, 'config.js'), 'utf8'), /voice: false/);
  assert.match(readFileSync(join(plain, 'demo.html'), 'utf8'), /static-demo\.js/);

  const withKeys = join(work, 'con-claves');
  const result = spawnSync('bash', ['scripts/build-static-demo.sh'], {
    cwd: repo, encoding: 'utf8',
    env: {...process.env, PUBLIC_SITE_URL: 'https://example.test', STATIC_DEMO_OUT: withKeys,
      LLM_API_KEY: 'sk-prueba', ELEVENLABS_API_KEY: 'el-prueba', ELEVENLABS_VOICE_ID: 'voz-prueba'},
  });
  successful(result);
  const config = readFileSync(join(withKeys, 'config.js'), 'utf8');
  assert.match(config, /aiChat: true/);
  assert.match(config, /voice: true/);
  assert.match(result.stdout, /IA activa/);
  assert.match(result.stdout, /Voz activa/);
});
