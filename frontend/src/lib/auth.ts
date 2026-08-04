const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8005";

export interface SessionUser {
  username: string;
}

export async function login(username: string, password: string): Promise<SessionUser> {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    throw new Error("Usuário ou senha inválidos");
  }
  return res.json();
}

export async function logout(): Promise<void> {
  await fetch(`${API_BASE}/api/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
}

export async function fetchSession(): Promise<SessionUser | null> {
  const res = await fetch(`${API_BASE}/api/auth/me`, {
    credentials: "include",
  });
  if (!res.ok) {
    return null;
  }
  return res.json();
}
