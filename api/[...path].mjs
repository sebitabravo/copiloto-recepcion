// Proxy de /api/* hacia el copiloto real, para que la página publicada hable con la IA de verdad.
//
// La landing vive en Vercel (estática) y el servicio `copiloto` corre en otro host (VPS, Fly, Render
// o un túnel para la presentación). Enrutar por aquí deja todo en el mismo origen: las claves nunca
// llegan al navegador, no hay CORS y las cookies del panel funcionan igual que en local.
//
// Se activa con COPILOTO_URL (por ejemplo https://copiloto.tu-dominio.cl). Sin esa variable la
// versión publicada sigue usando el guion estático del navegador y este endpoint responde 503.
const HOP_BY_HOP = new Set(['connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
  'te', 'trailer', 'transfer-encoding', 'upgrade', 'host', 'content-length', 'accept-encoding']);

export function targetUrl(base, originalUrl) {
  const incoming = new URL(originalUrl, 'http://local.invalid');
  const upstream = new URL(base);
  const prefix = upstream.pathname.replace(/\/+$/, '');
  return `${upstream.origin}${prefix}${incoming.pathname}${incoming.search}`;
}

export async function proxy(request, {fetchImpl = fetch, base = process.env.COPILOTO_URL} = {}) {
  if (!base) {
    return {status: 503, body: 'El backend de la demo no está configurado (falta COPILOTO_URL).'};
  }
  const headers = new Headers();
  for (const [name, value] of Object.entries(request.headers || {})) {
    if (!HOP_BY_HOP.has(name.toLowerCase())) headers.set(name, value);
  }
  const method = (request.method || 'GET').toUpperCase();
  const hasBody = !['GET', 'HEAD'].includes(method);
  let response;
  try {
    response = await fetchImpl(targetUrl(base, request.url), {
      method,
      headers,
      body: hasBody ? (typeof request.body === 'string' ? request.body : JSON.stringify(request.body ?? {})) : undefined,
      redirect: 'manual',
    });
  } catch (error) {
    return {status: 502, body: `El copiloto no respondió: ${error.message}`};
  }
  const out = new Headers();
  for (const [name, value] of response.headers) {
    if (!HOP_BY_HOP.has(name.toLowerCase())) out.set(name, value);
  }
  return {status: response.status, headers: out, body: Buffer.from(await response.arrayBuffer())};
}

// Adaptador HTTP: en Vercel el cuerpo del request llega parseado cuando es JSON.
export default async function handler(req, res) {
  const result = await proxy({
    method: req.method,
    url: req.url,
    headers: req.headers,
    body: req.body,
  });
  res.statusCode = result.status;
  if (result.headers) {
    for (const [name, value] of result.headers) res.setHeader(name, value);
  } else {
    res.setHeader('content-type', 'text/plain; charset=utf-8');
  }
  res.end(result.status === undefined ? '' : result.body);
}
