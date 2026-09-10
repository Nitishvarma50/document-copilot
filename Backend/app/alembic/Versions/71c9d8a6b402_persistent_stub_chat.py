"""Prepare protected, transactional persistent chat writes.

Revision ID: 71c9d8a6b402
Revises: 3c81ca3fef26

Forward repair for installations stamped at the initial revision; see
Docs/chat-backend-migrations.md before applying to any existing database.
"""

from alembic import op

revision = "71c9d8a6b402"
down_revision = "3c81ca3fef26"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    DO $$ BEGIN
      IF to_regclass('public.messages_citations') IS NOT NULL THEN
        IF to_regclass('public.message_citations') IS NOT NULL THEN
          RAISE EXCEPTION 'Both citation tables exist; reconcile manually';
        END IF;
        ALTER TABLE public.messages_citations RENAME TO message_citations;
      END IF;
    END $$;

    CREATE INDEX IF NOT EXISTS ix_chat_threads_owner_activity
      ON public.chat_threads(user_id, updated_at DESC, id DESC);
    CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_messages_thread_sequence_guard
      ON public.chat_messages(thread_id, sequence);
    CREATE INDEX IF NOT EXISTS ix_source_documents_ticker_fiscal_year
      ON public.source_documents(ticker, fiscal_year);

    ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
    ALTER TABLE public.chat_threads ENABLE ROW LEVEL SECURITY;
    ALTER TABLE public.chat_messages ENABLE ROW LEVEL SECURITY;
    ALTER TABLE public.source_documents ENABLE ROW LEVEL SECURITY;
    ALTER TABLE public.document_chunks ENABLE ROW LEVEL SECURITY;
    ALTER TABLE public.message_citations ENABLE ROW LEVEL SECURITY;

    DROP POLICY IF EXISTS user_select_own ON public.users;
    DROP POLICY IF EXISTS users_select_own ON public.users;
    CREATE POLICY users_select_own ON public.users FOR SELECT
      TO authenticated USING (auth.uid() = id);
    DROP POLICY IF EXISTS source_documents_select_authenticated
      ON public.document_chunks;
    DROP POLICY IF EXISTS source_documents_select_authenticated
      ON public.source_documents;
    CREATE POLICY source_documents_select_authenticated ON public.source_documents
      FOR SELECT TO authenticated USING (true);
    DROP POLICY IF EXISTS document_chunks_select_authenticated
      ON public.document_chunks;
    CREATE POLICY document_chunks_select_authenticated ON public.document_chunks
      FOR SELECT TO authenticated USING (true);
    DROP POLICY IF EXISTS chat_threads_select_own ON public.chat_threads;
    CREATE POLICY chat_threads_select_own ON public.chat_threads FOR SELECT
      TO authenticated USING (auth.uid() = user_id);
    DROP POLICY IF EXISTS chat_messages_select_own ON public.chat_messages;
    CREATE POLICY chat_messages_select_own ON public.chat_messages FOR SELECT
      TO authenticated USING (EXISTS (
        SELECT 1 FROM public.chat_threads t
        WHERE t.id = chat_messages.thread_id AND t.user_id = auth.uid()
      ));

    -- The browser must not forge assistant messages through PostgREST.
    REVOKE ALL ON public.chat_messages FROM PUBLIC, anon, authenticated;
    GRANT SELECT ON public.chat_threads, public.chat_messages TO authenticated;
    GRANT SELECT, INSERT, UPDATE, DELETE
      ON public.users, public.chat_threads, public.chat_messages TO service_role;

    CREATE TABLE public.chat_turns (
      message_id uuid PRIMARY KEY REFERENCES public.chat_messages(id) ON DELETE CASCADE,
      thread_id uuid NOT NULL REFERENCES public.chat_threads(id) ON DELETE CASCADE,
      assistant_id uuid NOT NULL UNIQUE,
      assistant_sequence integer NOT NULL CHECK (assistant_sequence > 0),
      attempt_id uuid NOT NULL,
      status text NOT NULL CHECK (status IN ('streaming', 'completed', 'interrupted')),
      lease_until timestamptz NOT NULL,
      UNIQUE (thread_id, assistant_sequence)
    );
    CREATE UNIQUE INDEX uq_chat_turns_one_active_thread
      ON public.chat_turns(thread_id) WHERE status = 'streaming';
    ALTER TABLE public.chat_turns ENABLE ROW LEVEL SECURITY;
    REVOKE ALL ON public.chat_turns FROM PUBLIC, anon, authenticated;
    GRANT SELECT, INSERT, UPDATE, DELETE ON public.chat_turns TO service_role;
    """)

    op.execute("""
    CREATE FUNCTION public.chat_create_thread(
      p_user_id uuid, p_email text, p_title text
    ) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER
    SET search_path = public, pg_temp SET lock_timeout = '5s' AS $$
    DECLARE t public.chat_threads;
    BEGIN
      IF p_user_id IS NULL OR p_email IS NULL OR length(p_email) > 320
         OR length(btrim(p_email)) = 0 OR p_title IS NULL
         OR length(btrim(p_title)) = 0 OR length(p_title) > 225 THEN
        RAISE SQLSTATE 'PT422' USING MESSAGE = 'Invalid thread';
      END IF;
      INSERT INTO public.users(id, email, display_name)
        VALUES (p_user_id, p_email, left(split_part(p_email, '@', 1), 225))
        ON CONFLICT (id) DO UPDATE SET email = EXCLUDED.email;
      INSERT INTO public.chat_threads(id, user_id, title)
        VALUES (gen_random_uuid(), p_user_id, btrim(p_title)) RETURNING * INTO t;
      RETURN to_jsonb(t);
    END $$;
    """)

    op.execute("""
    CREATE FUNCTION public.chat_accept_turn(
      p_user_id uuid, p_thread_id uuid, p_message_id uuid, p_text text
    ) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER
    SET search_path = public, pg_temp SET lock_timeout = '5s' AS $$
    DECLARE
      t public.chat_threads;
      turn public.chat_turns;
      message public.chat_messages;
      next_sequence integer;
      answer text;
      attempt uuid := gen_random_uuid();
    BEGIN
      IF p_text IS NULL OR length(btrim(p_text)) = 0 OR length(p_text) > 16000
         OR p_message_id IS NULL THEN
        RAISE SQLSTATE 'PT422' USING MESSAGE = 'Invalid message';
      END IF;
      -- Every write acquires this lock first, including completion and cleanup.
      SELECT * INTO t FROM public.chat_threads
        WHERE id = p_thread_id AND user_id = p_user_id FOR UPDATE;
      IF NOT FOUND THEN
        RAISE SQLSTATE 'PT404' USING MESSAGE = 'Thread not found';
      END IF;
      UPDATE public.chat_turns SET status = 'interrupted'
        WHERE thread_id = p_thread_id AND status = 'streaming'
          AND lease_until <= clock_timestamp();
      SELECT * INTO message FROM public.chat_messages WHERE id = p_message_id;
      IF FOUND THEN
        IF message.thread_id <> p_thread_id OR message.role <> 'user'
           OR message.content <> p_text THEN
          RAISE SQLSTATE 'PT409' USING MESSAGE = 'Message conflict';
        END IF;
        SELECT * INTO turn FROM public.chat_turns WHERE message_id = p_message_id;
        IF NOT FOUND THEN
          RAISE SQLSTATE 'PT409' USING MESSAGE = 'Legacy message cannot be retried';
        END IF;
        IF turn.status = 'completed' THEN
          SELECT content INTO answer FROM public.chat_messages
            WHERE id = turn.assistant_id AND thread_id = p_thread_id;
          IF answer IS NULL THEN
            RAISE SQLSTATE 'PT409' USING MESSAGE = 'Stored answer unavailable';
          END IF;
          RETURN jsonb_build_object('assistantId', turn.assistant_id,
            'attemptId', turn.attempt_id, 'replay', true, 'content', answer);
        END IF;
        IF turn.status = 'streaming' OR EXISTS (
          SELECT 1 FROM public.chat_turns WHERE thread_id = p_thread_id
            AND assistant_sequence > turn.assistant_sequence
        ) THEN
          RAISE SQLSTATE 'PT409' USING MESSAGE = 'Turn conflict';
        END IF;
      END IF;
      IF EXISTS (SELECT 1 FROM public.chat_turns
                 WHERE thread_id = p_thread_id AND status = 'streaming') THEN
        RAISE SQLSTATE 'PT409' USING MESSAGE = 'Thread is busy';
      END IF;
      IF turn.message_id IS NULL THEN
        SELECT greatest(
          coalesce((SELECT max(sequence) FROM public.chat_messages
                    WHERE thread_id = p_thread_id), 0),
          coalesce((SELECT max(assistant_sequence) FROM public.chat_turns
                    WHERE thread_id = p_thread_id), 0)
        ) + 1 INTO next_sequence;
        INSERT INTO public.chat_messages(id, thread_id, role, content, parts, sequence)
          VALUES (p_message_id, p_thread_id, 'user', p_text,
                  jsonb_build_array(jsonb_build_object('type', 'text', 'text', p_text)),
                  next_sequence);
        INSERT INTO public.chat_turns(message_id, thread_id, assistant_id,
          assistant_sequence, attempt_id, status, lease_until)
          VALUES (p_message_id, p_thread_id, gen_random_uuid(), next_sequence + 1,
                  attempt, 'streaming', clock_timestamp() + interval '90 seconds')
          RETURNING * INTO turn;
      ELSE
        UPDATE public.chat_turns SET status = 'streaming', attempt_id = attempt,
          lease_until = clock_timestamp() + interval '90 seconds'
          WHERE message_id = p_message_id RETURNING * INTO turn;
      END IF;
      UPDATE public.chat_threads SET updated_at = clock_timestamp(),
        title = CASE WHEN title = 'New chat' THEN left(btrim(p_text), 225)
                     ELSE title END
        WHERE id = p_thread_id;
      RETURN jsonb_build_object('assistantId', turn.assistant_id,
        'attemptId', turn.attempt_id, 'replay', false);
    END $$;
    """)

    op.execute("""
    CREATE FUNCTION public.chat_complete_turn(
      p_user_id uuid, p_thread_id uuid, p_assistant_id uuid,
      p_attempt_id uuid, p_text text
    ) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER
    SET search_path = public, pg_temp SET lock_timeout = '5s' AS $$
    DECLARE turn public.chat_turns;
    BEGIN
      PERFORM 1 FROM public.chat_threads
        WHERE id = p_thread_id AND user_id = p_user_id FOR UPDATE;
      IF NOT FOUND THEN
        RAISE SQLSTATE 'PT404' USING MESSAGE = 'Thread not found';
      END IF;
      SELECT * INTO turn FROM public.chat_turns
        WHERE assistant_id = p_assistant_id AND thread_id = p_thread_id;
      IF NOT FOUND OR turn.attempt_id <> p_attempt_id THEN
        RAISE SQLSTATE 'PT409' USING MESSAGE = 'Stale turn';
      END IF;
      IF turn.status = 'completed' THEN RETURN '{}'::jsonb; END IF;
      IF turn.status <> 'streaming' OR turn.lease_until <= clock_timestamp() THEN
        RAISE SQLSTATE 'PT409' USING MESSAGE = 'Stale turn';
      END IF;
      IF p_text IS NULL OR length(btrim(p_text)) = 0 OR length(p_text) > 16000 THEN
        RAISE SQLSTATE 'PT422' USING MESSAGE = 'Invalid answer';
      END IF;
      INSERT INTO public.chat_messages(id, thread_id, role, content, parts, sequence)
        VALUES (p_assistant_id, p_thread_id, 'assistant', p_text,
          jsonb_build_array(jsonb_build_object('type', 'text', 'text', p_text)),
          turn.assistant_sequence);
      UPDATE public.chat_turns SET status = 'completed'
        WHERE message_id = turn.message_id;
      UPDATE public.chat_threads SET updated_at = clock_timestamp()
        WHERE id = p_thread_id;
      RETURN '{}'::jsonb;
    END $$;
    """)

    op.execute("""
    CREATE FUNCTION public.chat_abandon_turn(
      p_user_id uuid, p_thread_id uuid, p_assistant_id uuid, p_attempt_id uuid
    ) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER
    SET search_path = public, pg_temp SET lock_timeout = '5s' AS $$
    BEGIN
      PERFORM 1 FROM public.chat_threads
        WHERE id = p_thread_id AND user_id = p_user_id FOR UPDATE;
      IF NOT FOUND THEN
        RAISE SQLSTATE 'PT404' USING MESSAGE = 'Thread not found';
      END IF;
      UPDATE public.chat_turns SET status = 'interrupted'
        WHERE thread_id = p_thread_id AND assistant_id = p_assistant_id
          AND attempt_id = p_attempt_id AND status = 'streaming';
      RETURN '{}'::jsonb;
    END $$;
    """)

    for signature in (
        "chat_create_thread(uuid, text, text)",
        "chat_accept_turn(uuid, uuid, uuid, text)",
        "chat_complete_turn(uuid, uuid, uuid, uuid, text)",
        "chat_abandon_turn(uuid, uuid, uuid, uuid)",
    ):
        op.execute(
            f"REVOKE ALL ON FUNCTION public.{signature} "
            "FROM PUBLIC, anon, authenticated"
        )
        op.execute(f"GRANT EXECUTE ON FUNCTION public.{signature} TO service_role")
    op.execute("NOTIFY pgrst, 'reload schema'")


def downgrade() -> None:
    # Do not silently delete coordination state or restore browser message writes.
    raise RuntimeError(
        "Persistent chat downgrade requires an explicit backup/rollback plan; "
        "automated destructive downgrade is disabled."
    )
