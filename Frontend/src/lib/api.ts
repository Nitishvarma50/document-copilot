import { http } from "./http";

export type AuthenticatedUser = {
  id: string;
  email: string | null;
};

export const api = {
  getAuthenticatedUser: () =>
    http.get<AuthenticatedUser>("/auth/me"),
};
