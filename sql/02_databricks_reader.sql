/* Read-only login for Databricks Lakehouse Federation.
   Run in the Azure portal: sqldb-nestle-erp > Query editor (login lloydsadmin), or in SSMS connected to sqldb-nestle-erp.
   Replace the password before running and keep it only in the Databricks connection. */
CREATE USER dbx_reader WITH PASSWORD = '<choose-a-strong-password>';
ALTER ROLE db_datareader ADD MEMBER dbx_reader;
