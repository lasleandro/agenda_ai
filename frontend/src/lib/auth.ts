const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

export class AuthRequestError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: string
  ) {
    super(message);
    this.name = "AuthRequestError";
  }
}

async function getAuthError(response: Response, fallback: string): Promise<AuthRequestError> {
  const body = await response.json().catch(() => null);
  return new AuthRequestError(
    body?.error?.message || fallback,
    response.status,
    body?.error?.code
  );
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
    throw await getAuthError(res, "Email ou senha inválidos");
  }
  return res.json();
}

export async function requestPasswordReset(email: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/auth/forgot-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  if (!res.ok) {
    throw await getAuthError(res, "Não foi possível solicitar a redefinição.");
  }
}

async function submitTokenPassword(
  path: "/api/auth/activate" | "/api/auth/reset-password",
  token: string,
  password: string,
  passwordConfirmation: string
): Promise<void> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      token,
      password,
      password_confirmation: passwordConfirmation,
    }),
  });
  if (!res.ok) {
    throw await getAuthError(res, "Não foi possível atualizar a senha.");
  }
}

export function activateAccount(
  token: string,
  password: string,
  passwordConfirmation: string
): Promise<void> {
  return submitTokenPassword("/api/auth/activate", token, password, passwordConfirmation);
}

export function resetPassword(
  token: string,
  password: string,
  passwordConfirmation: string
): Promise<void> {
  return submitTokenPassword("/api/auth/reset-password", token, password, passwordConfirmation);
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
  professionalId: string,
  { confirm = false }: { confirm?: boolean } = {}
): Promise<{ professional_id: string; professional_name: string }> {
  const res = await fetch(`${API_BASE}/api/auth/impersonate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ professional_id: professionalId, confirm }),
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
