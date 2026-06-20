export const API_BASE = 'http://127.0.0.1:8765';

export async function apiFetch(input: RequestInfo | URL, init?: RequestInit) {
  const response = await fetch(input, init);
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const message = typeof data.detail === 'string' ? data.detail : `请求失败：${response.status}`;
    throw new Error(message);
  }
  return response;
}

export async function apiJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const response = await apiFetch(input, init);
  return response.json() as Promise<T>;
}
