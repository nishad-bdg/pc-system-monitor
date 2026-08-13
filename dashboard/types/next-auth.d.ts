import "next-auth";
import type { DefaultSession } from "next-auth";

declare module "next-auth" {
  interface Session {
    user: {
      apiToken?: string;
    } & DefaultSession["user"];
  }

  interface User {
    apiToken?: string;
    refreshToken?: string;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    apiToken?: string;
    refreshToken?: string;
  }
}