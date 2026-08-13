import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";
import type { NextAuthConfig } from "next-auth";

function decodeJwtExp(token: string): number | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const payload = JSON.parse(Buffer.from(parts[1], "base64url").toString("utf-8"));
    return typeof payload.exp === "number" ? payload.exp * 1000 : null;
  } catch {
    return null;
  }
}

export const authConfig = {
  trustHost: true,
  pages: {
    signIn: "/login",
  },
  session: {
    strategy: "jwt",
    maxAge: 30 * 24 * 60 * 60, // 30 days — same horizon as the refresh token
  },
  providers: [
    Credentials({
      name: "credentials",
      credentials: {
        username: { label: "Username", type: "text" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        const apiUrl = process.env.API_URL ?? "http://127.0.0.1:8000";
        try {
          const res = await fetch(`${apiUrl}/auth/token`, {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: new URLSearchParams({
              username: credentials?.username as string,
              password: credentials?.password as string,
            }),
            cache: "no-store",
          });
          if (!res.ok) return null;
          const data = await res.json();
          let role: string | undefined;
          let groups: string[] | undefined;
          try {
            const me = await fetch(`${apiUrl}/auth/me`, {
              headers: { Authorization: `Bearer ${data.access_token}` },
              cache: "no-store",
            });
            if (me.ok) {
              const meJson = await me.json();
              role = meJson.role;
              groups = meJson.groups ?? [];
            }
          } catch {
            // fall back to JWT-only session; role comes from the token below
          }
          if (!role) {
            try {
              const parts = data.access_token.split(".");
              const payload = JSON.parse(
                Buffer.from(parts[1], "base64url").toString("utf-8"),
              );
              role = payload.role;
            } catch {
              // ignore
            }
          }
          return {
            id: credentials?.username as string,
            name: credentials?.username as string,
            apiToken: data.access_token,
            refreshToken: data.refresh_token,
            role,
            groups: groups ?? [],
          };
        } catch {
          return null;
        }
      },
    }),
  ],
  callbacks: {
    async jwt({ token, user }) {
      if (user) {
        token.apiToken = (user as { apiToken?: string }).apiToken;
        token.refreshToken = (user as { refreshToken?: string }).refreshToken;
        token.role = (user as { role?: string }).role;
        token.groups = (user as { groups?: string[] }).groups ?? [];
        token.name = user.name;
        return token;
      }
      // Silent rotation: refresh the access token shortly before it expires.
      const apiUrl = process.env.API_URL ?? "http://127.0.0.1:8000";
      const exp = token.apiToken ? decodeJwtExp(token.apiToken as string) : null;
      const needsRefresh = token.apiToken
        ? exp !== null && exp - Date.now() < 60_000
        : Boolean(token.refreshToken);
      if (needsRefresh && token.refreshToken) {
        try {
          const res = await fetch(`${apiUrl}/auth/refresh`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ refresh_token: token.refreshToken }),
            cache: "no-store",
          });
          if (res.ok) {
            const data = await res.json();
            token.apiToken = data.access_token;
            token.refreshToken = data.refresh_token;
          } else {
            // Refresh token no longer valid — drop it so the session logs out.
            token.apiToken = undefined;
            token.refreshToken = undefined;
          }
        } catch {
          // Leave as-is; retry on the next request.
        }
      }
      return token;
    },
    session({ session, token }) {
      session.user.apiToken = token.apiToken as string | undefined;
      session.user.role = token.role as string | undefined;
      session.user.groups = (token.groups as string[] | undefined) ?? [];
      session.user.name = token.name as string | undefined;
      return session;
    },
  },
} satisfies NextAuthConfig;

export const { handlers, auth, signIn, signOut } = NextAuth(authConfig);
