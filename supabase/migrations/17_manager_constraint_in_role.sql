-- First, drop the existing constraint
ALTER TABLE public.users DROP CONSTRAINT valid_role;

-- Then add the new constraint with 'manager' included
ALTER TABLE public.users ADD CONSTRAINT valid_role CHECK (
    (role)::text = any (
        array[
            'org_admin'::character varying,
            'end_user'::character varying,
            'manager'::character varying
        ]::text[]
    )
);