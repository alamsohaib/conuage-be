
-- Create pricing_plans table
CREATE TABLE public.pricing_plans (
    id uuid NOT NULL DEFAULT extensions.uuid_generate_v4(),
    name character varying(100) NOT NULL,
    cost decimal(10,2) NOT NULL,
    monthly_token_limit_per_user integer NOT NULL,
    daily_token_limit_per_user integer NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    is_active boolean DEFAULT true,
    CONSTRAINT pricing_plans_pkey PRIMARY KEY (id),
    CONSTRAINT pricing_plans_name_key UNIQUE (name),
    CONSTRAINT positive_cost CHECK (cost >= 0),
    CONSTRAINT positive_monthly_limit CHECK (monthly_token_limit_per_user >= 0),
    CONSTRAINT positive_daily_limit CHECK (daily_token_limit_per_user >= 0)
);

-- Add subscription-related columns to organizations
ALTER TABLE public.organizations
ADD COLUMN selected_pricing_plan_id uuid,
ADD COLUMN number_of_users_paid integer DEFAULT 0,
ADD COLUMN subscription_start_date timestamp with time zone,
ADD COLUMN subscription_end_date timestamp with time zone,
ADD CONSTRAINT organizations_pricing_plan_fkey 
    FOREIGN KEY (selected_pricing_plan_id) 
    REFERENCES pricing_plans(id) ON DELETE RESTRICT,
ADD CONSTRAINT positive_users_paid 
    CHECK (number_of_users_paid >= 0);

-- Add daily token limit to users table
ALTER TABLE public.users
ADD COLUMN daily_token_limit integer DEFAULT 0;

-- Create function to update user token limits when organization changes plan
CREATE OR REPLACE FUNCTION update_user_token_limits()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    -- Update daily token limits for all users in the organization
    IF NEW.selected_pricing_plan_id IS NOT NULL AND 
       (OLD.selected_pricing_plan_id IS NULL OR OLD.selected_pricing_plan_id != NEW.selected_pricing_plan_id) THEN
        UPDATE users
        SET daily_token_limit = (
            SELECT daily_token_limit_per_user 
            FROM pricing_plans 
            WHERE id = NEW.selected_pricing_plan_id
        )
        WHERE organization_id = NEW.id;
    END IF;
    
    RETURN NEW;
END;
$$;

-- Create trigger for updating user token limits
DROP TRIGGER IF EXISTS update_user_token_limits_trigger ON organizations;
CREATE TRIGGER update_user_token_limits_trigger
    AFTER UPDATE OF selected_pricing_plan_id
    ON organizations
    FOR EACH ROW
    EXECUTE FUNCTION update_user_token_limits();


-- Create trigger for token usage validation
DROP TRIGGER IF EXISTS validate_token_usage_trigger ON token_logs;
CREATE TRIGGER validate_token_usage_trigger
    BEFORE INSERT ON token_logs
    FOR EACH ROW
    EXECUTE FUNCTION validate_token_usage();

-- Grant necessary permissions
GRANT ALL ON public.pricing_plans TO service_role;
GRANT EXECUTE ON FUNCTION update_user_token_limits() TO service_role;


