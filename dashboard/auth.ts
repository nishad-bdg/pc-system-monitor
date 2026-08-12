import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";
import type { NextAuthConfig } from "next-auth";

export const authConfig = {
  trustHost: true,
  pages: {
    signIn: "/login",
  },
  session: {
    strategy: "jwt",
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
          return {
            id: credentials?.username as string,
            name: credentials?.username as string,
            apiToken: data.access_token,
          };
        } catch {
          return null;
        }
      },
    }),
  ],
  callbacks: {
    jwt({ token, user }) {
      if (user) {
        token.apiToken = (user as { apiToken?: string }).apiToken;
        token.name = user.name;
      }
      return token;
    },
    session({ session, token }) {
      session.user.apiToken = token.apiToken as string | undefined;
      session.user.name = token.name as string | undefined;
      return session;
    },
  },
} satisfies NextAuthConfig;

export const { handlers, auth, signIn, signOut } = NextAuth(authConfig);
