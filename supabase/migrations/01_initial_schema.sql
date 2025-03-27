-- Enable necessary extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Ensure proper schema permissions
GRANT USAGE ON SCHEMA public TO postgres, anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA public TO postgres, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO postgres, service_role;
GRANT ALL ON ALL ROUTINES IN SCHEMA public TO postgres, service_role;

-- Create organizations table
CREATE TABLE IF NOT EXISTS public.organizations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    address TEXT DEFAULT '',
    country VARCHAR(100) DEFAULT '',
    state VARCHAR(100) DEFAULT '',
    city VARCHAR(100) DEFAULT '',
    post_code VARCHAR(20) DEFAULT '',
    is_active BOOLEAN DEFAULT true,
    auto_signup_enabled BOOLEAN DEFAULT false,
    token_balance FLOAT DEFAULT 0,
    monthly_token_limit INTEGER DEFAULT 1000,
    primary_contact_id UUID DEFAULT NULL,
    default_location_id UUID DEFAULT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create locations table
CREATE TABLE IF NOT EXISTS public.locations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    details TEXT,
    organization_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create users table
CREATE TABLE IF NOT EXISTS public.users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) NOT NULL UNIQUE,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    organization_id UUID NOT NULL REFERENCES public.organizations(id),
    location_id UUID NOT NULL REFERENCES public.locations(id),
    role VARCHAR(50) NOT NULL DEFAULT 'end_user',  -- 'org_admin', 'manager', or 'end_user'
    email_verified BOOLEAN DEFAULT false,
    status VARCHAR(50) DEFAULT 'pending',  -- 'pending', 'active', 'inactive'
    last_login TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT valid_role CHECK (role IN ('org_admin', 'manager', 'end_user')),
    CONSTRAINT valid_status CHECK (status IN ('pending', 'active', 'inactive'))
);

-- Create verification codes table
CREATE TABLE IF NOT EXISTS public.verification_codes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    code VARCHAR(6) NOT NULL,
    type VARCHAR(50) NOT NULL,  -- 'email_verification', 'password_reset'
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    used BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT valid_type CHECK (type IN ('email_verification', 'password_reset'))
);

-- Grant permissions on the organizations table
GRANT ALL ON public.organizations TO service_role;
GRANT ALL ON public.organizations TO postgres;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.organizations TO authenticated;
GRANT SELECT ON public.organizations TO anon;

-- Grant permissions on the locations table
GRANT ALL ON public.locations TO service_role;
GRANT ALL ON public.locations TO postgres;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.locations TO authenticated;
GRANT SELECT ON public.locations TO anon;

-- Grant permissions on the users table
GRANT ALL ON public.users TO service_role;
GRANT ALL ON public.users TO postgres;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.users TO authenticated;
GRANT SELECT ON public.users TO anon;

-- Grant permissions on the verification_codes table
GRANT ALL ON public.verification_codes TO service_role;
GRANT ALL ON public.verification_codes TO postgres;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.verification_codes TO authenticated;

-- Enable Row Level Security
ALTER TABLE public.organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.locations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.verification_codes ENABLE ROW LEVEL SECURITY;

-- Create policies for organizations
DROP POLICY IF EXISTS "Enable read access for all users" ON public.organizations;
CREATE POLICY "Enable read access for all users" ON public.organizations
    FOR SELECT
    TO public
    USING (true);

DROP POLICY IF EXISTS "Enable insert for service role" ON public.organizations;
CREATE POLICY "Enable insert for service role" ON public.organizations
    FOR INSERT
    TO service_role
    WITH CHECK (true);

DROP POLICY IF EXISTS "Enable update for service role" ON public.organizations;
CREATE POLICY "Enable update for service role" ON public.organizations
    FOR UPDATE
    TO service_role
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS "Enable delete for service role" ON public.organizations;
CREATE POLICY "Enable delete for service role" ON public.organizations
    FOR DELETE
    TO service_role
    USING (true);

-- Create policies for locations
DROP POLICY IF EXISTS "Enable read access for all users" ON public.locations;
CREATE POLICY "Enable read access for all users" ON public.locations
    FOR SELECT
    TO public
    USING (true);

DROP POLICY IF EXISTS "Enable insert for service role" ON public.locations;
CREATE POLICY "Enable insert for service role" ON public.locations
    FOR INSERT
    TO service_role
    WITH CHECK (true);

DROP POLICY IF EXISTS "Enable update for service role" ON public.locations;
CREATE POLICY "Enable update for service role" ON public.locations
    FOR UPDATE
    TO service_role
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS "Enable delete for service role" ON public.locations;
CREATE POLICY "Enable delete for service role" ON public.locations
    FOR DELETE
    TO service_role
    USING (true);

-- Create policies for users
DROP POLICY IF EXISTS "Users can view their own data" ON public.users;
CREATE POLICY "Users can view their own data" ON public.users
    FOR SELECT
    TO authenticated
    USING (id = auth.uid());

DROP POLICY IF EXISTS "Service role can manage users" ON public.users;
CREATE POLICY "Service role can manage users" ON public.users
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- Create policies for verification codes
DROP POLICY IF EXISTS "Users can view their own verification codes" ON public.verification_codes;
CREATE POLICY "Users can view their own verification codes" ON public.verification_codes
    FOR SELECT
    TO authenticated
    USING (user_id = auth.uid());

DROP POLICY IF EXISTS "Service role can manage verification codes" ON public.verification_codes;
CREATE POLICY "Service role can manage verification codes" ON public.verification_codes
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- Grant usage on the uuid-ossp extension
GRANT USAGE ON SCHEMA extensions TO postgres, service_role;
GRANT ALL ON ALL FUNCTIONS IN SCHEMA extensions TO postgres, service_role;

-- Alter default privileges for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT ALL ON TABLES TO postgres, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES TO anon;
