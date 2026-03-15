BEGIN TRY
    BEGIN TRANSACTION;

    IF COL_LENGTH('dbo.inscripciones', 'login_email') IS NULL
        ALTER TABLE dbo.inscripciones ADD login_email NVARCHAR(255) NULL;

    IF COL_LENGTH('dbo.inscripciones', 'password_hash') IS NULL
        ALTER TABLE dbo.inscripciones ADD password_hash NVARCHAR(255) NULL;

    IF COL_LENGTH('dbo.inscripciones', 'image_url') IS NULL
        ALTER TABLE dbo.inscripciones ADD image_url NVARCHAR(500) NULL;

    IF COL_LENGTH('dbo.dim_restaurants', 'login_email') IS NULL
        ALTER TABLE dbo.dim_restaurants ADD login_email NVARCHAR(255) NULL;

    IF COL_LENGTH('dbo.dim_restaurants', 'password_hash') IS NULL
        ALTER TABLE dbo.dim_restaurants ADD password_hash NVARCHAR(255) NULL;

    IF COL_LENGTH('dbo.dim_restaurants', 'image_url') IS NULL
        ALTER TABLE dbo.dim_restaurants ADD image_url NVARCHAR(500) NULL;

    IF NOT EXISTS (
        SELECT 1
        FROM sys.indexes
        WHERE name = 'ux_dim_restaurants_login_email'
    )
        CREATE UNIQUE INDEX ux_dim_restaurants_login_email
        ON dbo.dim_restaurants(login_email)
        WHERE login_email IS NOT NULL;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;

    THROW;
END CATCH;