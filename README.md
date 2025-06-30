# 🇸🇦 ZATCA Integration for ERPNext

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) ![ERPNext](https://img.shields.io/badge/ERPNext-Compatible-blue.svg) [![ERPNext](https://img.shields.io/badge/Frappe%20Cloud-Ready-green.svg)](https://frappecloud.com) [![ZATCA Phase 2](https://img.shields.io/badge/ZATCA-Phase%202%20Compliant-red.svg)](https://zatca.gov.sa)

A comprehensive ZATCA Phase 2 e-invoicing solution for ERPNext. Simple to install, powerful in functionality, and ready for production in minutes with full compliance to Saudi Arabia's electronic invoicing regulations.

## Overview

This ERPNext integration provides complete ZATCA (Zakat, Tax and Customs Authority) Phase 2 compliance for businesses operating in Saudi Arabia. The solution streamlines electronic invoicing with automated B2B clearance and B2C reporting workflows, multi-currency support, and comprehensive audit trails. From installation to go-live, businesses can achieve full ZATCA compliance quickly and efficiently.

## Key Features

### **📋 Invoice Management**
- **B2B Standard Invoices** - Complete clearance workflow for Business Customers (B2B)
- **B2C Simplified Invoices** - Reporting workflow for Individual Customers (B2C)
- **Credit Notes** - Credit note processing with ZATCA compliance (B2B and B2C)
- **Multi-Currency Support** - SAR and USD invoicing with currency conversion
- **Invoice Retention** - Retention management with ZATCA compliance (Fixed Amount OR Percentage)

### **🏢 Multi-Entity Support**
- **Multi-Company Operations** - Support for multiple entities with different VAT/CR numbers
- **Multi-Branch Configuration** - Branch-specific settings and operations with same or different CR
- **Data Validation** - Comprehensive validation before ZATCA submission for error-proof processing
- **Environment Management** - Fatoora Simulation and production environment support - test in simulation first and then enable production


### **⚡ Technical Features**
- **Real-time and Batch Processing** - Invoice clearance and reporting workflows in real-time, share your invoices with customers instantly
- **XML & QR Generation** - Automatic generation of compliant XML and QR codes with built-in print formats and email capabilities
- **Testing Environments** - Support for both ZATCA Simulation and Production portals
- **Audit Trail** - Complete tracking of all ZATCA requests and responses with detailes Tab in Sales invlice 

### **📊 Tax Compliance**
- **Standard Rate (15%)** - VAT compliance for standard transactions
- **Zero Rate** - Export and qualifying zero-rated supplies
- **Exempt Rate** - Tax-exempt transactions with proper documentation
- **Customer Scenarios** - Local customers, international customers, VAT/non-VAT combinations

### **📈 Reporting**
- **VAT Reports** - VAT collected and payable reports
- **Sales Reports** - Sales reporting for tax filing purposes
- **Transaction Logs** - Detailed transaction history and status tracking
- **Built-in Print Formats** - Professional invoice templates ready for use

### **🌐 Cloud & Environment Support**
- **Frappe Cloud Optimized** - Fully compatible with Frappe Cloud hosting
- **Multiple ZATCA Environments** - Support for sandbox, simulation, and production
- **Environment Switching** - Easy migration from testing to live environments
- **Cloud-Native Architecture** - Built for scalability and performance

## 🔧 Quick Installation

### Prerequisites
- ERPNext v14+ or v15+
- Python 3.10+
- Valid ZATCA CSR and certificates

### Installation Steps

1. **Install the App**
   ```bash
   # Get the app
   bench get-app https://github.com/beverensoftware/zatca_integration.git
   
   # Install on your site
   bench --site [site-name] install-app zatca_integration
   ```

2. **Setup ZATCA Configuration**
   ```bash
   # Run setup wizard
   bench --site [site-name] migrate
   ```

3. **Configure Your Company**
   - Navigate to Company Settings
   - Enable ZATCA E-Invoicing
   - Upload your ZATCA certificates
   - Configure tax templates

### 🏗️ Development Setup

1. **Create Development Site**
   ```bash
   bench new-site zatca.local
   bench --site zatca.local install-app erpnext
   bench --site zatca.local install-app zatca_integration
   bench --site zatca.local add-to-hosts
   ```

2. **Development Commands**
   ```bash
   # Start development server
   bench start
   
   # Run migrations
   bench --site zatca.local migrate
   
   # Clear cache
   bench --site zatca.local clear-cache
   ```

## ⚙️ Configuration Guide

### 1. **Generate Production CSID**
1. **Provide Company Information** - Enter your company registration details, tax information, and VAT number, then create CSR
2. **Create Compliance CSID** - From CSR, create Compliance CSID using OTP and validate CSID
3. **Generate Production CSID** - Generate Production CSID from validated Compliance CSID

### 2. **Company Configuration**
- Enable ZATCA e-invoicing phase2 in company master by selecting the Production CSID
- Check if Date Enforcement is enabled or not (enabling is recommended to avoid ZATCA fines)

### 3. **Sales Taxes and Charges Template**
1. Configure Tax Type: Standard vs Zero or Exempt
2. For Zero and Exempt rates, choose appropriate reason if you use these tax types

### 4. **Purchase Taxes and Charges Template**
1. Configure Tax Type: Standard vs Zero or Exempt  
2. For Zero and Exempt rates, choose appropriate reason if you use these tax types

### 5. **Customer Setup**
- Customer country and name in Arabic are mandatory
- Customer VAT information setup in ZATCA tab
- Customer must have a valid Primary address



## 🧪 Testing & Validation

### Progressive Testing Approach
1. **Simulation Environment** - Test with ZATCA Simulation environment first for all validation. Once validated, enable production mode and go live.

### Validation Features
1. **Automatic Processing** - Upon submission, details are automatically sent to ZATCA once enabled
2. **XML and QR Validation** - Validate the XML and QR code after invoice submission
3. **Status Monitoring** - List view will show ZATCA status: cleared, reported, or error if any
4. **Detailed E-Invoice Tab** - A detailed E-Invoice Details tab with all ZATCA information will be available
5. **Transaction Records** - All transactions to ZATCA are recorded in ZATCA Transactions for review


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