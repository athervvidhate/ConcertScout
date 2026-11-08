import { createClient, type Session, type SupabaseClient } from "@supabase/supabase-js";
import { useSyncExternalStore } from "react";

import { API_URL, refusal } from "@/lib/search";

const URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const KEY = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
// Where a sign-in link or Google returns to, and where it should go from there.
export const CONFIRM_PATH = "/auth/confirm";
const RETURN_KEY = "concert-scout-return-to";

/** Accounts are optional. Without Supabase settings the site has no sign-in at all. */
export const accountsEnabled = Boolean(URL && KEY);

export type AccountState =
  | { status: "off" }
  | { status: "loading" }
  | { status: "guest" }
  | { status: "signed-in"; id: string; email: string; methods: string[] };

const OFF: AccountState = { status: "off" };
const LOADING: AccountState = { status: "loading" };
const GUEST: AccountState = { status: "guest" };

let client: SupabaseClient | null = null;
let state: AccountState = accountsEnabled ? LOADING : OFF;
let watching = false;
const listeners = new Set<() => void>();

function supabase(): SupabaseClient {
  if (!URL || !KEY) throw new Error("Accounts are off");
  // The confirm page exchanges a returned code itself, so no other page acts on its URL.
  client ??= createClient(URL, KEY, { auth: { flowType: "pkce", detectSessionInUrl: false } });
  return client;
}

function fromSession(session: Session | null): AccountState {
  if (!session) return GUEST;
  const { id, email, identities } = session.user;
  return {
    status: "signed-in",
    id,
    email: email ?? "",
    methods: (identities ?? []).map((identity) => identity.provider),
  };
}

function update(next: AccountState) {
  const same =
    next.status === state.status &&
    (next.status !== "signed-in" || (state.status === "signed-in" && state.id === next.id));
  if (same) return;
  state = next;
  listeners.forEach((listener) => listener());
}

export function subscribeAccount(listener: () => void): () => void {
  listeners.add(listener);
  if (accountsEnabled && !watching) {
    watching = true;
    supabase().auth.onAuthStateChange((_, session) => update(fromSession(session)));
  }
  return () => listeners.delete(listener);
}

export function currentAccount(): AccountState {
  return state;
}

export function useAccount(): AccountState {
  return useSyncExternalStore(
    subscribeAccount,
    () => state,
    () => (accountsEnabled ? LOADING : OFF),
  );
}

export class AccountError extends Error {}

function explain(error: { code?: string; message: string }): AccountError {
  const messages: Record<string, string> = {
    invalid_credentials: "That email and password do not match an account.",
    email_not_confirmed: "Confirm your email first. Check your inbox for the link.",
    user_already_exists: "That email already has an account. Sign in instead.",
    weak_password: "Choose a longer password, at least 8 characters.",
    over_email_send_rate_limit: "Too many emails sent. Wait a few minutes and try again.",
    over_request_rate_limit: "Too many tries. Wait a few minutes and try again.",
    same_password: "Choose a password you have not used here before.",
    otp_expired: "That link has expired or was already used. Ask for a new one.",
  };
  return new AccountError(messages[error.code ?? ""] ?? "That did not work. Try again.");
}

function confirmUrl(): string {
  return `${window.location.origin}${CONFIRM_PATH}`;
}

/** The confirm page sends the person back here once they are signed in. */
export function rememberReturn(path: string): void {
  try {
    sessionStorage.setItem(RETURN_KEY, path);
  } catch {}
}

export function takeReturn(): string {
  try {
    const path = sessionStorage.getItem(RETURN_KEY);
    sessionStorage.removeItem(RETURN_KEY);
    if (path?.startsWith("/") && !path.startsWith("//")) return path;
  } catch {}
  return "/";
}

export async function signIn(email: string, password: string): Promise<void> {
  const { error } = await supabase().auth.signInWithPassword({ email, password });
  if (error) throw explain(error);
}

/** Resolves once the confirmation email is on its way. */
export async function signUp(email: string, password: string): Promise<void> {
  const { data, error } = await supabase().auth.signUp({
    email,
    password,
    options: { emailRedirectTo: confirmUrl() },
  });
  if (error) throw explain(error);
  // Supabase hides whether an email is taken by answering with an identity-less user.
  if (data.user && data.user.identities?.length === 0) {
    throw explain({ code: "user_already_exists", message: "" });
  }
}

export async function resendConfirmation(email: string): Promise<void> {
  const { error } = await supabase().auth.resend({
    type: "signup",
    email,
    options: { emailRedirectTo: confirmUrl() },
  });
  if (error) throw explain(error);
}

/** Leaves the site for Google, which returns to the confirm page. */
export async function signInWithGoogle(): Promise<void> {
  const { error } = await supabase().auth.signInWithOAuth({
    provider: "google",
    options: { redirectTo: confirmUrl() },
  });
  if (error) throw explain(error);
}

/** Always answers the same way, so the form never reveals whether an email has an account. */
export async function sendPasswordReset(email: string): Promise<void> {
  const { error } = await supabase().auth.resetPasswordForEmail(email, {
    redirectTo: confirmUrl(),
  });
  if (error && error.code?.startsWith("over_")) throw explain(error);
}

export type Confirmed = "signed-in" | "recovery";

/** Completes a Google return (`code`) or an email link (`token_hash`). */
export async function confirm(params: URLSearchParams): Promise<Confirmed> {
  const auth = supabase().auth;
  // Google answers a cancelled or refused sign-in with an error instead of a code.
  if (params.get("error")) throw new AccountError("Sign-in was cancelled. Nothing changed.");
  const code = params.get("code");
  const tokenHash = params.get("token_hash");
  const type = params.get("type");
  if (code) {
    const { error } = await auth.exchangeCodeForSession(code);
    if (error) throw explain(error);
    return "signed-in";
  }
  if (tokenHash && (type === "email" || type === "recovery")) {
    const { error } = await auth.verifyOtp({ token_hash: tokenHash, type });
    if (error) throw explain({ ...error, code: error.code ?? "otp_expired" });
    return type === "recovery" ? "recovery" : "signed-in";
  }
  throw explain({ code: "otp_expired", message: "" });
}

export async function choosePassword(password: string): Promise<void> {
  const { error } = await supabase().auth.updateUser({ password });
  if (error) throw explain(error);
}

export async function signOut(): Promise<void> {
  await supabase().auth.signOut();
  update(GUEST);
}

/** Forgets this device's session without asking Supabase, which no longer has the account. */
async function forgetSession(): Promise<void> {
  await supabase().auth.signOut({ scope: "local" });
  update(GUEST);
}

/** The current access token, refreshed when it has expired. */
export async function accessToken(): Promise<string> {
  const { data } = await supabase().auth.getSession();
  const token = data.session?.access_token;
  if (!token) throw new AccountError("Sign in to use your account.");
  return token;
}

/** A request to the API as the signed-in person. */
export async function accountFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${await accessToken()}`);
  if (init.body) headers.set("Content-Type", "application/json");
  const response = await fetch(`${API_URL}/account${path}`, { ...init, headers });
  if (!response.ok) throw await refusal(response);
  return response;
}

export async function deleteAccount(): Promise<void> {
  await accountFetch("", { method: "DELETE" });
  await forgetSession();
}
