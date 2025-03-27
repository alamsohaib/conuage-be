-- Add token tracking columns to users table
ALTER TABLE users
ADD COLUMN IF NOT EXISTS chat_tokens_used bigint DEFAULT 0,
ADD COLUMN IF NOT EXISTS embedding_tokens_used bigint DEFAULT 0;

-- Add token tracking columns to organizations table
ALTER TABLE organizations
ADD COLUMN IF NOT EXISTS chat_tokens_used bigint DEFAULT 0,
ADD COLUMN IF NOT EXISTS embedding_tokens_used bigint DEFAULT 0;

-- Create token tracking log table
CREATE TABLE IF NOT EXISTS token_logs (
    id uuid DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id uuid REFERENCES users(id) ON DELETE CASCADE,
    organization_id uuid REFERENCES organizations(id) ON DELETE CASCADE,
    token_type text NOT NULL CHECK (token_type IN ('chat', 'embedding')),
    operation_type text NOT NULL CHECK (operation_type IN ('chat_completion', 'document_processing')),
    tokens_used int NOT NULL,
    document_id uuid REFERENCES documents(id) ON DELETE SET NULL,
    chat_id uuid REFERENCES chats(id) ON DELETE SET NULL,
    created_at timestamptz DEFAULT now()
);

-- Add RLS policies for token_logs
ALTER TABLE token_logs ENABLE ROW LEVEL SECURITY;

-- Allow users to view their own token logs
CREATE POLICY "Users can view their own token logs"
    ON token_logs FOR SELECT
    USING (auth.uid()::text = user_id::text);

-- Allow org admins to view all token logs for their organization
CREATE POLICY "Org admins can view all token logs for their organization"
    ON token_logs FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM users
            WHERE users.id = auth.uid()
            AND users.organization_id = token_logs.organization_id
            AND users.role = 'org_admin'
        )
    );

-- Function to update user and org token counts
CREATE OR REPLACE FUNCTION update_token_counts()
RETURNS TRIGGER AS $$
BEGIN
    -- Update user token counts
    IF NEW.token_type = 'chat' THEN
        UPDATE users
        SET chat_tokens_used = chat_tokens_used + NEW.tokens_used
        WHERE id = NEW.user_id;
        
        UPDATE organizations
        SET chat_tokens_used = chat_tokens_used + NEW.tokens_used
        WHERE id = NEW.organization_id;
    ELSE
        UPDATE users
        SET embedding_tokens_used = embedding_tokens_used + NEW.tokens_used
        WHERE id = NEW.user_id;
        
        UPDATE organizations
        SET embedding_tokens_used = embedding_tokens_used + NEW.tokens_used
        WHERE id = NEW.organization_id;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for token count updates
CREATE TRIGGER update_token_counts_after_insert
    AFTER INSERT ON token_logs
    FOR EACH ROW
    EXECUTE FUNCTION update_token_counts();
