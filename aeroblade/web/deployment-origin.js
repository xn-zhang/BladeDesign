// Keep the HTTP host policy aligned with bridge/deployment_origin.py.
export function canConnectService(url, pageProtocol) {
  if (url.protocol === 'https:') return true;
  if (url.protocol !== 'http:' || pageProtocol !== 'http:') return false;
  if (['localhost', '[::1]'].includes(url.hostname)) return true;
  const parts = url.hostname.split('.');
  if (parts.length !== 4 || parts.some(p => !/^\d+$/.test(p) || Number(p) > 255)) return false;
  const [a,b] = parts.map(Number);
  return a === 10 || a === 127 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168);
}
