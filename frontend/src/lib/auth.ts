const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

export class AuthRequestError extends Error {
  constructor(
    message: string,
    public readonly status: number
  ) {
    super(message);
    this.name = "AuthRequestError";
  }
}

export interface SessionUser {
  user_id: string;
  email: string;
  role: "platform_admin" | "professional";
  professional_id: string | null;
  professional_name: string | null;
  impersonating: boolean;
  features: string[];
}

export function sessionHasFeature(user: SessionUser | null, featureKey: string): boolean {
  return user?.features.includes(featureKey) ?? false;
}

export async function login(email: string, password: string): Promise<{ email: string; role: string }> {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    throw new Error("Email ou senha inválidos");
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
    cache: "no-store",
  });
  if (!res.ok) {
    return null;
  }
  return res.json();
}

export async function impersonate(
  professionalId: string
): Promise<{ professional_id: string; professional_name: string }> {
  const res = await fetch(`${API_BASE}/api/auth/impersonate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ professional_id: professionalId }),
  });
  if (!res.ok) {
    throw new AuthRequestError("Failed to impersonate tenant", res.status);
  }
  return res.json();
}

export async function stopImpersonating(): Promise<void> {
  const res = await fetch(`${API_BASE}/api/auth/stop-impersonating`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok) {
    throw new Error("Failed to stop impersonating");
  }
}
