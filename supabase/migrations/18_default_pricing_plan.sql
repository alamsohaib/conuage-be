-- Add default column to pricing_plans table
ALTER TABLE public.pricing_plans 
ADD COLUMN "default" boolean NOT NULL DEFAULT false;

-- Add partial unique index to ensure only one default plan
CREATE UNIQUE INDEX idx_pricing_plans_default 
ON public.pricing_plans ((1))
WHERE "default" = true;

-- Create a trigger to enforce single default plan
CREATE OR REPLACE FUNCTION check_default_pricing_plan()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.default = true THEN
        -- Set all other plans to non-default
        UPDATE public.pricing_plans
        SET "default" = false
        WHERE id != NEW.id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ensure_single_default_plan
    BEFORE INSERT OR UPDATE ON public.pricing_plans
    FOR EACH ROW
    WHEN (NEW.default = true)
    EXECUTE FUNCTION check_default_pricing_plan();