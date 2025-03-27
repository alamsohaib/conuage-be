-- Create user_locations junction table
CREATE TABLE IF NOT EXISTS public.user_locations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    location_id UUID NOT NULL REFERENCES public.locations(id) ON DELETE CASCADE,
    is_primary BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, location_id)
);

-- Add index for faster lookups
CREATE INDEX idx_user_locations_user_id ON public.user_locations(user_id);
CREATE INDEX idx_user_locations_location_id ON public.user_locations(location_id);

-- Grant permissions on the user_locations table
GRANT ALL ON public.user_locations TO service_role;
GRANT ALL ON public.user_locations TO postgres;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.user_locations TO authenticated;

-- Enable Row Level Security
ALTER TABLE public.user_locations ENABLE ROW LEVEL SECURITY;

-- Create policies for user_locations
CREATE POLICY "Enable read access for users in same organization" ON public.user_locations
    FOR SELECT
    TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.users u1, public.users u2
            WHERE u1.id = user_locations.user_id
            AND u2.id = auth.uid()
            AND u1.organization_id = u2.organization_id
        )
    );

CREATE POLICY "Enable insert for org admins" ON public.user_locations
    FOR INSERT
    TO authenticated
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.users u
            WHERE u.id = auth.uid()
            AND u.role = 'org_admin'
            AND u.organization_id = (
                SELECT organization_id FROM public.users
                WHERE id = user_locations.user_id
            )
        )
    );

CREATE POLICY "Enable update for org admins" ON public.user_locations
    FOR UPDATE
    TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.users u
            WHERE u.id = auth.uid()
            AND u.role = 'org_admin'
            AND u.organization_id = (
                SELECT organization_id FROM public.users
                WHERE id = user_locations.user_id
            )
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.users u
            WHERE u.id = auth.uid()
            AND u.role = 'org_admin'
            AND u.organization_id = (
                SELECT organization_id FROM public.users
                WHERE id = user_locations.user_id
            )
        )
    );

CREATE POLICY "Enable delete for org admins" ON public.user_locations
    FOR DELETE
    TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.users u
            WHERE u.id = auth.uid()
            AND u.role = 'org_admin'
            AND u.organization_id = (
                SELECT organization_id FROM public.users
                WHERE id = user_locations.user_id
            )
        )
    );

-- Add trigger to ensure at least one primary location
CREATE OR REPLACE FUNCTION public.ensure_primary_location()
RETURNS TRIGGER AS $$
BEGIN
    -- If this is an insert and is_primary is true, set all other locations for this user to false
    IF (TG_OP = 'INSERT' OR TG_OP = 'UPDATE') AND NEW.is_primary = true THEN
        UPDATE public.user_locations
        SET is_primary = false
        WHERE user_id = NEW.user_id AND id != NEW.id;
    END IF;

    -- If this is the only location for the user, make it primary
    IF TG_OP = 'INSERT' AND NOT EXISTS (
        SELECT 1 FROM public.user_locations
        WHERE user_id = NEW.user_id AND id != NEW.id
    ) THEN
        NEW.is_primary := true;
    END IF;

    -- Ensure at least one primary location exists
    IF TG_OP = 'UPDATE' AND OLD.is_primary = true AND NEW.is_primary = false AND NOT EXISTS (
        SELECT 1 FROM public.user_locations
        WHERE user_id = NEW.user_id AND id != NEW.id AND is_primary = true
    ) THEN
        RAISE EXCEPTION 'User must have at least one primary location';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ensure_primary_location_trigger
    BEFORE INSERT OR UPDATE ON public.user_locations
    FOR EACH ROW
    EXECUTE FUNCTION public.ensure_primary_location();

-- Migrate existing data
INSERT INTO public.user_locations (user_id, location_id, is_primary)
SELECT id, location_id, true
FROM public.users;

-- Update users table to make location_id nullable
ALTER TABLE public.users ALTER COLUMN location_id DROP NOT NULL;
