-- For document_embeddings table
ALTER TABLE public.document_embeddings 
ALTER COLUMN embedding TYPE vector(3072);

-- For document_images table
ALTER TABLE public.document_images 
ALTER COLUMN embedding TYPE vector(3072);

-- For document_tables table
ALTER TABLE public.document_tables 
ALTER COLUMN embedding TYPE vector(3072);


-- old search all content folder (unchanged)


BEGIN
    RETURN QUERY
    -- Search in document_embeddings (text and tables)
    SELECT
        1 - (de.embedding <=> query_embedding) as similarity,
        de.content,
        de.content_type,
        jsonb_build_object(
            'document_id', de.document_id,
            'page_number', de.page_number,
            'document_name', d.name,
            'file_path', d.file_path
        ) as additional_info
    FROM
        document_embeddings de
        JOIN documents d ON d.id = de.document_id
    WHERE
        de.location_id = ANY(location_ids)
        AND de.embedding IS NOT NULL
        AND 1 - (de.embedding <=> query_embedding) > match_threshold
    
    UNION ALL
    
    -- Search in document_images
    SELECT
        1 - (di.embedding <=> query_embedding) as similarity,
        COALESCE(di.description, 'Image content') as content,
        'image' as content_type,
        jsonb_build_object(
            'document_id', di.document_id,
            'page_number', di.page_number,
            'image_number', di.image_number,
            'storage_path', di.storage_path,
            'document_name', d.name,
            'file_path', d.file_path
        ) as additional_info
    FROM
        document_images di
        JOIN documents d ON d.id = di.document_id
    WHERE
        di.location_id = ANY(location_ids)
        AND di.embedding IS NOT NULL
        AND 1 - (di.embedding <=> query_embedding) > match_threshold
    
    UNION ALL
    
    -- Search in document_tables
    SELECT
        1 - (dt.embedding <=> query_embedding) as similarity,
        COALESCE(dt.description, dt.html_content, 'Table content') as content,
        'table' as content_type,
        jsonb_build_object(
            'document_id', dt.document_id,
            'page_number', dt.page_number,
            'table_number', dt.table_number,
            'table_content', dt.content,
            'html_content', dt.html_content,
            'document_name', d.name,
            'file_path', d.file_path
        ) as additional_info
    FROM
        document_tables dt
        JOIN documents d ON d.id = dt.document_id
    WHERE
        dt.location_id = ANY(location_ids)
        AND dt.embedding IS NOT NULL
        AND 1 - (dt.embedding <=> query_embedding) > match_threshold
    
    ORDER BY similarity DESC
    LIMIT match_count;
END;
