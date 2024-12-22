## Saudi Arabia Electronic Invoicing

### Local setup

1. Install Local Site
    ```
    bench new-site zatca.local
    bench --site zatca.local install-app erpnext
    bench --site zatca.local install-app zatca_integration
    bench --site zatca.local add-to-hosts
    ```
2. Drop Local Site
    ```
    bench drop-site zatca.local --force
    ```
3. Restore Local Site from Backup
    ```
    bench --site zatca.local --force restore /Users/shakir/Downloads/20240808_014526-amcc-test_frappe_cloud-database.sql.gz --with-private-files /Users/shakir/Downloads/20240808_014526-amcc-test_frappe_cloud-private-files.tar --with-public-files /Users/shakir/Downloads/20240808_014526-amcc-test_frappe_cloud-files.tar
    ```