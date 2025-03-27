-- Create token blacklist table
CREATE TABLE public.token_blacklist (
    id uuid NOT NULL DEFAULT extensions.uuid_generate_v4(),
    token text NOT NULL,
    user_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    expires_at timestamp with time zone NOT NULL,
    CONSTRAINT token_blacklist_pkey PRIMARY KEY (id),
    CONSTRAINT token_blacklist_token_key UNIQUE (token),
    CONSTRAINT token_blacklist_user_id_fkey FOREIGN KEY (user_id) 
        REFERENCES public.users(id) ON DELETE CASCADE
);

-- Add index for faster token lookups
CREATE INDEX idx_token_blacklist_token ON public.token_blacklist(token);

-- Add index for cleanup of expired tokens
CREATE INDEX idx_token_blacklist_expires_at ON public.token_blacklist(expires_at);