# 🇸🇦 ZATCA Integration for ERPNext 

[![CI](https://github.com/Beveren-Software-Inc/zatca_integration/actions/workflows/ci.yml/badge.svg)](https://github.com/Beveren-Software-Inc/zatca_integration/actions/workflows/ci.yml)

## Overview

This app delivers clean, powerful features that are simple to install and configure for Saudi Arabia's ZATCA e-invoicing compliance. Streamline your B2B clearance and B2C reporting workflows with automated XML generation, digital signing, and real-time ZATCA integration.

**Perfect for SMBs and enterprises** looking for reliable, easy-to-use ZATCA compliance without the complexity. No SDK downloads or complex setup required - just install, configure, and go live with foolproof ZATCA integration trusted by many enterprises and SMBs across the Kingdom.

## Key Features

### **📋 Core Invoice Processing**
- **B2B Standard Invoices** - Complete clearance workflow for business customers
- **B2C Simplified Invoices** - Reporting workflow for individual customers  
- **Credit Notes** - Full ZATCA compliance for both B2B and B2C
- **Multi-Currency Support** - SAR and USD with automatic conversion
- **Invoice Retention** - Fixed amount or percentage retention management

### **🏢 System Features**
- **Multi-Company & Multi-Branch** - Support for multiple entities and branches
- **Real-time and Batch Processing** - Instant invoice clearance and customer sharing
- **XML & QR Generation** - Automatic compliant document generation
- **Environment Management** - Simulation and production environments
- **Complete Audit Trail** - Full tracking of all ZATCA interactions

### **📊 Tax & Compliance**
- **All VAT Rates** - Standard (15%), Zero, and Exempt rate support
- **Customer Scenarios** - Local, international, VAT/non-VAT handling
- **Data Validation** - Comprehensive pre-submission validation
- **Built-in Reports** - VAT, sales, and transaction reporting

### **🌐 Frappe Cloud Ready**
- **Frappe Cloud Optimized** - Full compatibility and scalability
- **Environment Switching** - Easy migration from Simulation to production

## 🔧 Quick Installation

### Prerequisites
- ERPNext v14+ or v15+
- Python 3.10+
- Valid ZATCA CSR and certificates

### Installation Steps

```bash
# Get and install the app
bench get-app https://github.com/beverensoftware/zatca_integration.git
bench --site [site-name] install-app zatca_integration
bench --site [site-name] migrate
```

## ⚙️ Configuration Guide

### 1. **Generate Production CSID**

#### Step 1.1: Provide Company Information (Generate CSR)
Enter your company registration details, tax information, and VAT number, then generate CSR.

![Company Information](docs/screenshots/Generate_CSR.png)

#### Step 1.2: Create Compliance CSID  
From CSR, create Compliance CSID using OTP and validate CSID.

![Compliance CSID Creation](docs/screenshots/Generate_CSID.png)

#### Step 1.3: Generate Production CSID
Generate Production CSID from validated Compliance CSID.

![Production CSID Generation](docs/screenshots/Generate_PSID.png)

### 2. **Company Configuration**

  i. *Enable ZATCA E-Invoicing*  
Activates ZATCA Phase 2 integration for the company.  
Once enabled, all invoices will be validated according to ZATCA’s e-invoicing rules.

ii. *ZATCA Phase*  
Select which ZATCA Phase applies to your company. For ongoing compliance, choose **ZATCA Phase 2**.

iii. *Production CSID (Phase 2 Only)*
<br/>Enter the **Production CSID** that contains your ZATCA certificate.  
In sandbox/testing mode, this field may display **Sandbox**.  
In production, you must configure the official Production CSID to ensure invoices are legally valid.

iv. *Enforce Date Validation* 
<br/>Ensures that invoice dates strictly follow ZATCA’s requirements. Recommended to keep this **enabled** to avoid ZATCA fines caused by incorrect or backdated entries.

v. *Enable Multi-Sales Invoice on Credit Note*  
Not directly tied to ZATCA compliance.  
Useful if you want to issue a **single credit note** that applies to multiple sales invoices.  
Example: If a customer returns goods from different invoices, you can generate one consolidated credit note.

vi. *Enable Sales Retention*  
Designed for project-based billing.  
Example: You bill 75% now and retain 25% until project completion.  
With this option enabled, ERPNext allows entry of **retention amounts** in sales invoices.  
**Note for ZATCA:** The retention is still included in the invoice total sent to ZATCA, assuming the full project value is invoiced.

vii *B2C Auto Sales Submission + Submission Frequency*  
-   **B2C Auto Sales Submission Enabled:** Switches from real-time submission to batch submission for high-volume retail invoices.
    
-   **Sales Information Submission Frequency:** Appears only when auto submission is enabled; sets how often invoices are submitted in bulk (e.g., every 2 hours, daily).

![Company Configuration](docs/screenshots/Company_Settings.png)

### 3. **Sales and Purchase Taxes and Charges Template**
1. Configure Tax Type: Standard vs Zero or Exempt
2. For Zero and Exempt rates, choose the appropriate reason if you use these tax types
3. This is important for correct VAT report calculation and reporting

![Tax Templates Configuration](docs/screenshots/Salestax_Template.png)

### 4. **Customer Setup**
- Customer Name and Arabic name are mandatory
- Customer Country is mandatory (defaults to Saudi Arabia)
- Customer VAT information setup in ZATCA tab
- Customer must have a valid primary address

![Customer Setup](docs/screenshots/Customer_Settings.png)

### 5. **Invoice Processing**
- Now start submitting your invoices and they will be automatically reported to ZATCA
- Seamless and real-time integration with ZATCA systems

![Invoice Processing](docs/screenshots/Sales_Invoices.png)

### 6. **VAT Reports and Audit Logs**
- VAT reports will be ready for you to file your taxes in any period - monthly or quarterly
- All transactions are recorded in the system including error codes that can be navigated from the workspace quickly and easily

![VAT Reports](docs/screenshots/ZATCA_Workspace.png)

## 🛠️ Support & Documentation

### Getting Help
- **Support Email**: support@beverensoftware.com
- **Issues**: Report bugs via GitHub issues

### Requirements
- Valid ZATCA registration and certificates
- ERPNext system administrator access
- Basic understanding of Saudi tax regulations

## 🏢 About Beveren Software

Beveren Software provides ERP solutions and digital transformation services in the Middle East, specializing in:

- ERPNext Implementation & Customization
- ZATCA Compliance Solutions  
- Digital Transformation Consulting
- Cloud Migration Services
- Enterprise Integration Solutions

### Contact Information
- **Website**: [beverensoftware.com](https://beverensoftware.com)
- **Email**: info@beverensoftware.com
- **Support**: support@beverensoftware.com
- **LinkedIn**: [Beveren Software](https://linkedin.com/company/beveren-software)

---

*Developed by Beveren Software for the Saudi business community*
