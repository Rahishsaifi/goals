export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

export function csrfToken(): string {
  if (typeof document === "undefined") {
    return "";
  }
  return (
    document.cookie
      .split("; ")
      .find((row) => row.startsWith("ri_csrf="))
      ?.split("=")[1] ?? ""
  );
}

export async function readApiError(response: Response, fallback: string): Promise<string> {
  const body = (await response.json().catch(() => null)) as
    | { detail?: string; error?: { message?: string } }
    | null;
  return body?.error?.message ?? body?.detail ?? fallback;
}
