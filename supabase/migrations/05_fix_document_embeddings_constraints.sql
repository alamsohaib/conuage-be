-- First, let's check and drop any existing constraints
DO $$ 
BEGIN
    -- Drop the content constraint if it exists
    IF EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'document_embeddings_document_id_page_number_content_key'
    ) THEN
        ALTER TABLE document_embeddings 
        DROP CONSTRAINT document_embeddings_document_id_page_number_content_key;
    END IF;
    
    -- Drop the page constraint if it exists
    IF EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'document_embeddings_document_id_page_number_key'
    ) THEN
        ALTER TABLE document_embeddings 
        DROP CONSTRAINT document_embeddings_document_id_page_number_key;
    END IF;
END $$;

-- Add the new constraint
ALTER TABLE document_embeddings 
ADD CONSTRAINT document_embeddings_document_id_page_number_key 
UNIQUE (document_id, page_number);

-- Update the upsert function
CREATE OR REPLACE FUNCTION upsert_document_embedding(
    p_document_id UUID,
    p_location_id UUID,
    p_page_number INTEGER,
    p_content TEXT,
    p_embedding FLOAT[],
    p_created_at TIMESTAMP WITH TIME ZONE,
    p_updated_at TIMESTAMP WITH TIME ZONE
) RETURNS SETOF document_embeddings AS $$
BEGIN
    RETURN QUERY
    INSERT INTO document_embeddings (
        document_id,
        location_id,
        page_number,
        content,
        embedding,
        created_at,
        updated_at
    ) VALUES (
        p_document_id,
        p_location_id,
        p_page_number,
        p_content,
        p_embedding::vector,
        p_created_at,
        p_updated_at
    )
    ON CONFLICT (document_id, page_number) 
    DO UPDATE SET
        content = EXCLUDED.content,
        embedding = EXCLUDED.embedding,
        location_id = EXCLUDED.location_id,
        updated_at = EXCLUDED.updated_at
    RETURNING *;
END;
$$ LANGUAGE plpgsql;

