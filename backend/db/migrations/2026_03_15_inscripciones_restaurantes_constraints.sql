/*
Migración SQL Server:
- Dejar inscripciones solo con estado pendiente.
- Estandarizar valores a inglés y una palabra.
- Añadir restricciones tipo ENUM (CHECK) para segmento, terraza y cuisine_type.
*/

BEGIN TRY
    BEGIN TRANSACTION;

    /* 1) Normalizar estado pendiente */
    UPDATE dbo.inscripciones
    SET estado_inscripcion = 'pendiente'
    WHERE LOWER(LTRIM(RTRIM(COALESCE(estado_inscripcion, '')))) IN ('pendiente');

    /* 2) Eliminar registros no pendientes de inscripciones */
    DELETE FROM dbo.inscripciones
    WHERE LOWER(LTRIM(RTRIM(COALESCE(estado_inscripcion, '')))) <> 'pendiente';

    /* 3) Normalizar/migrar SEGMENT */
    UPDATE dbo.inscripciones
    SET restaurant_segment = CASE LOWER(LTRIM(RTRIM(COALESCE(restaurant_segment, ''))))
        WHEN 'gourmet' THEN 'gourmet'
        WHEN 'traditional' THEN 'traditional'
        WHEN 'tradicional' THEN 'traditional'
        WHEN 'business' THEN 'business'
        WHEN 'family' THEN 'family'
        ELSE restaurant_segment
    END;

    UPDATE dbo.dim_restaurants
    SET restaurant_segment = CASE LOWER(LTRIM(RTRIM(COALESCE(restaurant_segment, ''))))
        WHEN 'gourmet' THEN 'gourmet'
        WHEN 'traditional' THEN 'traditional'
        WHEN 'tradicional' THEN 'traditional'
        WHEN 'business' THEN 'business'
        WHEN 'family' THEN 'family'
        ELSE restaurant_segment
    END;

    /* 4) Normalizar/migrar TERRACE */
    UPDATE dbo.inscripciones
    SET terrace_setup_type = CASE LOWER(LTRIM(RTRIM(COALESCE(terrace_setup_type, ''))))
        WHEN 'todo el año' THEN 'yearround'
        WHEN 'todo el ano' THEN 'yearround'
        WHEN 'yearround' THEN 'yearround'
        WHEN 'solo verano' THEN 'summer'
        WHEN 'summer' THEN 'summer'
        WHEN 'no tiene' THEN 'none'
        WHEN 'none' THEN 'none'
        ELSE terrace_setup_type
    END;

    UPDATE dbo.dim_restaurants
    SET terrace_setup_type = CASE LOWER(LTRIM(RTRIM(COALESCE(terrace_setup_type, ''))))
        WHEN 'todo el año' THEN 'yearround'
        WHEN 'todo el ano' THEN 'yearround'
        WHEN 'yearround' THEN 'yearround'
        WHEN 'solo verano' THEN 'summer'
        WHEN 'summer' THEN 'summer'
        WHEN 'no tiene' THEN 'none'
        WHEN 'none' THEN 'none'
        ELSE terrace_setup_type
    END;

        /* 5) Normalizar/migrar CUISINE */
        UPDATE dbo.inscripciones
        SET cuisine_type = CASE LOWER(LTRIM(RTRIM(COALESCE(cuisine_type, ''))))
                WHEN 'grill' THEN 'grill'
                WHEN 'parrilla y brasa' THEN 'grill'
            WHEN 'spanish' THEN 'spanish'
            WHEN 'cocina española' THEN 'spanish'
            WHEN 'cocina espanola' THEN 'spanish'
                WHEN 'mediterranean' THEN 'mediterranean'
                WHEN 'cocina mediterránea' THEN 'mediterranean'
                WHEN 'cocina mediterranea' THEN 'mediterranean'
                WHEN 'guisos y estofados' THEN 'stew'
                WHEN 'stew' THEN 'stew'
                WHEN 'fritura andaluza' THEN 'fried'
                WHEN 'fried' THEN 'fried'
                WHEN 'italian' THEN 'italian'
                WHEN 'italiana' THEN 'italian'
                WHEN 'asiática (japonesa, china, sudeste asiático)' THEN 'asian'
                WHEN 'asiatica (japonesa, china, sudeste asiatico)' THEN 'asian'
                WHEN 'asian' THEN 'asian'
                WHEN 'latinoamericana (mexicana, peruana)' THEN 'latin'
                WHEN 'latin' THEN 'latin'
                WHEN 'turca/árabe' THEN 'arabic'
                WHEN 'turca/arabe' THEN 'arabic'
                WHEN 'arabic' THEN 'arabic'
                WHEN 'cocina de vanguardia y autor' THEN 'avantgarde'
                WHEN 'avantgarde' THEN 'avantgarde'
                WHEN 'plant-based (vegetariana/vegana)' THEN 'plantbased'
                WHEN 'plantbased' THEN 'plantbased'
                WHEN 'street food' THEN 'streetfood'
                WHEN 'streetfood' THEN 'streetfood'
                ELSE cuisine_type
        END;

        UPDATE dbo.dim_restaurants
        SET cuisine_type = CASE LOWER(LTRIM(RTRIM(COALESCE(cuisine_type, ''))))
                WHEN 'grill' THEN 'grill'
                WHEN 'parrilla y brasa' THEN 'grill'
            WHEN 'spanish' THEN 'spanish'
            WHEN 'cocina española' THEN 'spanish'
            WHEN 'cocina espanola' THEN 'spanish'
                WHEN 'mediterranean' THEN 'mediterranean'
                WHEN 'cocina mediterránea' THEN 'mediterranean'
                WHEN 'cocina mediterranea' THEN 'mediterranean'
                WHEN 'guisos y estofados' THEN 'stew'
                WHEN 'stew' THEN 'stew'
                WHEN 'fritura andaluza' THEN 'fried'
                WHEN 'fried' THEN 'fried'
                WHEN 'italian' THEN 'italian'
                WHEN 'italiana' THEN 'italian'
                WHEN 'asiática (japonesa, china, sudeste asiático)' THEN 'asian'
                WHEN 'asiatica (japonesa, china, sudeste asiatico)' THEN 'asian'
                WHEN 'asian' THEN 'asian'
                WHEN 'latinoamericana (mexicana, peruana)' THEN 'latin'
                WHEN 'latin' THEN 'latin'
                WHEN 'turca/árabe' THEN 'arabic'
                WHEN 'turca/arabe' THEN 'arabic'
                WHEN 'arabic' THEN 'arabic'
                WHEN 'cocina de vanguardia y autor' THEN 'avantgarde'
                WHEN 'avantgarde' THEN 'avantgarde'
                WHEN 'plant-based (vegetariana/vegana)' THEN 'plantbased'
                WHEN 'plantbased' THEN 'plantbased'
                WHEN 'street food' THEN 'streetfood'
                WHEN 'streetfood' THEN 'streetfood'
                ELSE cuisine_type
        END;

        /* 6) Eliminar filas fuera de catálogo en inscripciones */
        DELETE FROM dbo.inscripciones
        WHERE restaurant_segment IS NOT NULL
            AND restaurant_segment NOT IN ('gourmet', 'traditional', 'business', 'family');

    DELETE FROM dbo.inscripciones
    WHERE terrace_setup_type IS NOT NULL
            AND terrace_setup_type NOT IN ('yearround', 'summer', 'none');

    DELETE FROM dbo.inscripciones
    WHERE cuisine_type IS NOT NULL
      AND cuisine_type NOT IN (
        'grill',
                'spanish',
        'mediterranean',
        'stew',
        'fried',
        'italian',
        'asian',
        'latin',
        'arabic',
        'avantgarde',
        'plantbased',
        'streetfood'
      );

    /* 7) Re-crear constraints con nuevo catálogo */
    IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'ck_inscripciones_estado_pendiente')
        ALTER TABLE dbo.inscripciones DROP CONSTRAINT ck_inscripciones_estado_pendiente;
    IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'ck_inscripciones_segment')
        ALTER TABLE dbo.inscripciones DROP CONSTRAINT ck_inscripciones_segment;
    IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'ck_inscripciones_terrace')
        ALTER TABLE dbo.inscripciones DROP CONSTRAINT ck_inscripciones_terrace;
    IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'ck_inscripciones_cuisine')
        ALTER TABLE dbo.inscripciones DROP CONSTRAINT ck_inscripciones_cuisine;

    IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'ck_dim_restaurants_segment')
        ALTER TABLE dbo.dim_restaurants DROP CONSTRAINT ck_dim_restaurants_segment;
    IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'ck_dim_restaurants_terrace')
        ALTER TABLE dbo.dim_restaurants DROP CONSTRAINT ck_dim_restaurants_terrace;
    IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'ck_dim_restaurants_cuisine')
        ALTER TABLE dbo.dim_restaurants DROP CONSTRAINT ck_dim_restaurants_cuisine;

    ALTER TABLE dbo.inscripciones WITH CHECK
    ADD CONSTRAINT ck_inscripciones_estado_pendiente
    CHECK (LOWER(LTRIM(RTRIM(COALESCE(estado_inscripcion, '')))) = 'pendiente');

    ALTER TABLE dbo.inscripciones WITH CHECK
    ADD CONSTRAINT ck_inscripciones_segment
    CHECK (restaurant_segment IS NULL OR restaurant_segment IN ('gourmet', 'traditional', 'business', 'family'));

    ALTER TABLE dbo.inscripciones WITH CHECK
    ADD CONSTRAINT ck_inscripciones_terrace
    CHECK (terrace_setup_type IS NULL OR terrace_setup_type IN ('yearround', 'summer', 'none'));

    ALTER TABLE dbo.inscripciones WITH CHECK
    ADD CONSTRAINT ck_inscripciones_cuisine
    CHECK (
        cuisine_type IS NULL OR cuisine_type IN (
            'grill',
            'spanish',
            'mediterranean',
            'stew',
            'fried',
            'italian',
            'asian',
            'latin',
            'arabic',
            'avantgarde',
            'plantbased',
            'streetfood'
        )
    );

    ALTER TABLE dbo.dim_restaurants WITH CHECK
    ADD CONSTRAINT ck_dim_restaurants_segment
    CHECK (restaurant_segment IS NULL OR restaurant_segment IN ('gourmet', 'traditional', 'business', 'family'));

    ALTER TABLE dbo.dim_restaurants WITH CHECK
    ADD CONSTRAINT ck_dim_restaurants_terrace
    CHECK (terrace_setup_type IS NULL OR terrace_setup_type IN ('yearround', 'summer', 'none'));

    ALTER TABLE dbo.dim_restaurants WITH CHECK
    ADD CONSTRAINT ck_dim_restaurants_cuisine
    CHECK (
        cuisine_type IS NULL OR cuisine_type IN (
            'grill',
            'spanish',
            'mediterranean',
            'stew',
            'fried',
            'italian',
            'asian',
            'latin',
            'arabic',
            'avantgarde',
            'plantbased',
            'streetfood'
        )
    );

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;

    THROW;
END CATCH;
