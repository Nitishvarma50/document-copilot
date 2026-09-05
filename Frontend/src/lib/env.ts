type PublicEnv = {
  apiBaseUrl: string;
  supabaseUrl: string;
  supabaseAnonKey: string;
};

function requireEnv(name: string): string {
  const value = import.meta.env[name];

  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`Missing required frontend environment variable: ${name}`);
  }

  return value.trim();
}

function requireUrl(name: string): string {
  const value = requireEnv(name);

  try {
    new URL(value);
  } catch {
    throw new Error(`Frontend environment variable ${name} must be a valid URL`);
  }

  return value.replace(/\/$/, "");
}

export const env: PublicEnv = Object.freeze({
  apiBaseUrl: requireUrl("VITE_API_BASE_URL"),
  supabaseUrl: requireUrl("VITE_SUPABASE_URL"),
  supabaseAnonKey: requireEnv("VITE_SUPABASE_ANON_KEY"),
});
