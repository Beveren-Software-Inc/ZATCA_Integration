# 🇸🇦 ZATCA Integration for ERPNext 

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
- Enable ZATCA e-invoicing phase2 in company master by selecting the Production CSID
- Check if Date Enforcement is enabled or not (enabling is recommended to avoid ZATCA fines)

![Company Configuration](docs/screenshots/step4-company-configuration.png)

### 3. **Sales Taxes and Charges Template**
1. Configure Tax Type: Standard vs Zero or Exempt
2. For Zero and Exempt rates, choose appropriate reason if you use these tax types

![Tax Templates Configuration](docs/screenshots/step5-tax-templates.png)

### 4. **Customer Setup**
- Customer country and name in Arabic are mandatory
- Customer VAT information setup in ZATCA tab
- Customer must have a valid Primary address

![Customer Setup](docs/screenshots/step6-customer-setup.png)

![Customer ZATCA Tab](docs/screenshots/step6-customer-zatca-tab.png)


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
