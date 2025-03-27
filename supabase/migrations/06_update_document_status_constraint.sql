-- Drop existing check constraint if it exists
DO $$ 
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'valid_status'
    ) THEN
        ALTER TABLE documents 
        DROP CONSTRAINT valid_status;
    END IF;
END $$;

-- Add updated check constraint with new status values
ALTER TABLE documents
ADD CONSTRAINT valid_status 
CHECK (status IN ('pending', 'added', 'processing', 'processed', 'error'));