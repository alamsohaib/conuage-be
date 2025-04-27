-- Create demo bookings table
CREATE TABLE public.demo_bookings (
    id uuid NOT NULL DEFAULT extensions.uuid_generate_v4(),
    name text NOT NULL,
    email character varying(255) NOT NULL,
    phone character varying(50),
    services_interested jsonb NOT NULL DEFAULT '{}',
    how_can_we_help text,
    where_did_you_hear text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT demo_bookings_pkey PRIMARY KEY (id),
    CONSTRAINT demo_bookings_email_check CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')
);

-- Add index on email for faster lookups
CREATE INDEX idx_demo_bookings_email ON public.demo_bookings(email);