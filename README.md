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

### Space Top Setup
1. Install Local Site
    ```
    bench new-site spacetop.local
    bench --site spacetop.local install-app erpnext
    bench --site spacetop.local install-app lending
    bench --site spacetop.local install-app hrms
    bench --site spacetop.local install-app ksa_hrms
    bench --site spacetop.local install-app hr_addon
    bench --site spacetop.local install-app zatca_integration
    bench --site spacetop.local install-app beveren_spacetop_app 
    bench --site spacetop.local add-to-hosts
    ```
2. Drop Local Site
    ```
    bench drop-site spacetop.local --force
    ```
3. Restore Local Site from Backup
    ```
    bench --site spacetop.local --force restore /Users/shakir/Downloads/20250113_183443-spacetopco_frappe_cloud-database.sql.gz \
    --with-private-files /Users/shakir/Downloads/20250113_183443-spacetopco_frappe_cloud-private-files.tar \
    --with-public-files /Users/shakir/Downloads/20250113_183443-spacetopco_frappe_cloud-files.tar
    ```