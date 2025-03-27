-- Add daily token columns to users table
ALTER TABLE public.users
ADD COLUMN IF NOT EXISTS daily_chat_tokens_used integer NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS daily_document_processing_tokens_used integer NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS last_daily_reset timestamp with time zone DEFAULT CURRENT_TIMESTAMP;

-- Add daily token columns to organizations table
ALTER TABLE public.organizations
ADD COLUMN IF NOT EXISTS daily_chat_tokens_used integer NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS daily_document_processing_tokens_used integer NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS last_daily_reset timestamp with time zone DEFAULT CURRENT_TIMESTAMP;

-- Drop existing function if it exists
DROP FUNCTION IF EXISTS update_token_counts CASCADE;
DROP FUNCTION IF EXISTS reset_daily_counts_if_needed CASCADE;
DROP FUNCTION IF EXISTS reset_all_daily_counts CASCADE;

-- Create function to reset all daily counts
CREATE OR REPLACE FUNCTION public.reset_all_daily_counts()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    now_time timestamp with time zone;
BEGIN
    now_time := CURRENT_TIMESTAMP;
    
    -- Reset all users
    UPDATE users
    SET 
        daily_chat_tokens_used = 0,
        daily_document_processing_tokens_used = 0,
        last_daily_reset = now_time;
    
    -- Reset all organizations
    UPDATE organizations
    SET 
        daily_chat_tokens_used = 0,
        daily_document_processing_tokens_used = 0,
        last_daily_reset = now_time;
END;
$$;

-- Create function to check and reset daily counts
CREATE OR REPLACE FUNCTION public.reset_daily_counts_if_needed(user_id_param uuid, org_id_param uuid)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    now_time timestamp with time zone;
BEGIN
    now_time := CURRENT_TIMESTAMP;
    
    -- Reset user daily counts if needed
    UPDATE users
    SET 
        daily_chat_tokens_used = 0,
        daily_document_processing_tokens_used = 0,
        last_daily_reset = now_time
    WHERE 
        id = user_id_param 
        AND (
            last_daily_reset IS NULL 
            OR date_trunc('day', now_time) > date_trunc('day', last_daily_reset)
        );
    
    -- Reset organization daily counts if needed
    UPDATE organizations
    SET 
        daily_chat_tokens_used = 0,
        daily_document_processing_tokens_used = 0,
        last_daily_reset = now_time
    WHERE 
        id = org_id_param 
        AND (
            last_daily_reset IS NULL 
            OR date_trunc('day', now_time) > date_trunc('day', last_daily_reset)
        );
END;
$$;

-- Create updated token counting function
CREATE OR REPLACE FUNCTION public.update_token_counts()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    -- Check and reset daily counts if needed (more than 24 hours since last reset)
    PERFORM reset_daily_counts_if_needed(NEW.user_id, NEW.organization_id);
    
    -- Update user token counts based on operation_type
    IF NEW.operation_type = 'chat' THEN
        UPDATE users
        SET 
            chat_tokens_used = chat_tokens_used + NEW.tokens_used,
            daily_chat_tokens_used = daily_chat_tokens_used + NEW.tokens_used
        WHERE id = NEW.user_id;
        
        UPDATE organizations
        SET 
            chat_tokens_used = chat_tokens_used + NEW.tokens_used,
            daily_chat_tokens_used = daily_chat_tokens_used + NEW.tokens_used
        WHERE id = NEW.organization_id;
    ELSE -- operation_type is 'document_processing'
        UPDATE users
        SET 
            document_processing_tokens_used = document_processing_tokens_used + NEW.tokens_used,
            daily_document_processing_tokens_used = daily_document_processing_tokens_used + NEW.tokens_used
        WHERE id = NEW.user_id;
        
        UPDATE organizations
        SET 
            document_processing_tokens_used = document_processing_tokens_used + NEW.tokens_used,
            daily_document_processing_tokens_used = daily_document_processing_tokens_used + NEW.tokens_used
        WHERE id = NEW.organization_id;
    END IF;
    
    RETURN NEW;
END;
$$;

-- Create trigger for token counting
DROP TRIGGER IF EXISTS update_token_counts_after_insert ON token_logs;
CREATE TRIGGER update_token_counts_after_insert
    AFTER INSERT ON token_logs
    FOR EACH ROW
    EXECUTE FUNCTION update_token_counts();

-- Grant necessary permissions
GRANT EXECUTE ON FUNCTION public.reset_all_daily_counts() TO service_role;
GRANT EXECUTE ON FUNCTION public.reset_daily_counts_if_needed(uuid, uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.update_token_counts() TO service_role;

-- Note: For Supabase, you'll need to set up the cron job through the Supabase dashboard
-- Go to Database -> Database Functions -> New Scheduled Function
-- Schedule: 0 0 * * * (runs at midnight)
-- Function to run: select reset_all_daily_counts();