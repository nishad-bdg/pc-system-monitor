import "next-auth";
import type { DefaultSession } from "next-auth";

declare module "next-auth" {
  interface Session {
    user: {
      apiToken?: string;
      role?: string;
      groups?: string[];
    } & DefaultSession["user"];
  }

  interface User {
    apiToken?: string;
    refreshToken?: string;
    role?: string;
    groups?: string[];
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    apiToken?: string;
    refreshToken?: string;
    role?: string;
    groups?: string[];
  }
}