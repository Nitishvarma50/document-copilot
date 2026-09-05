import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../auth/useAuth";
import { api } from "../lib/api";
import { HttpError } from "../lib/http";
import type { AuthenticatedUser } from "../lib/api";

export function HomePage() {
  const navigate = useNavigate();
  const { signOut, user } = useAuth();
  const [backendUser, setBackendUser] = useState<AuthenticatedUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    void api
      .getAuthenticatedUser()
      .then((authenticatedUser) => {
        if (isMounted) {
          setBackendUser(authenticatedUser);
        }
      })
      .catch(async (requestError: unknown) => {
        if (!isMounted) {
          return;
        }

        if (requestError instanceof HttpError && requestError.status === 401) {
          await signOut();
          navigate("/login", { replace: true });
          return;
        }

        setError("We could not verify your backend session.");
      })
      .finally(() => {
        if (isMounted) {
          setIsLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [navigate, signOut]);

  return (
    <main className="home-shell">
      <section className="home-card" aria-labelledby="home-title">
        <p className="eyebrow">Document Copilot</p>
        <h1 id="home-title">Your research workspace</h1>
        <p>
          Signed in through Supabase as <strong>{user?.email}</strong>.
        </p>

        {isLoading && <p role="status">Verifying your backend session…</p>}
        {error && <p className="form-error" role="alert">{error}</p>}
        {backendUser && (
          <p className="form-message" role="status">
            Backend verified user: {backendUser.email ?? backendUser.id}
          </p>
        )}

        <button type="button" onClick={() => void signOut()}>
          Sign out
        </button>
      </section>
    </main>
  );
}
