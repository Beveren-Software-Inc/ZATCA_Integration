// Regression checks for the quick-entry half of public/js/customer_address.js.
// Runs without a browser or a bench site:
//
//   node zatca_integration/test/js/test_quick_entry_address.js
//
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const code = fs.readFileSync(
  path.join(__dirname, "..", "..", "public", "js", "customer_address.js"),
  "utf8"
);

let dom_ready;
const timers = [];

function makeInput(value) {
  return {
    _value: value,
    val() {
      return this._value;
    },
    on() {},
    off() {},
  };
}

class FakeField {
  constructor(df, value) {
    this.df = Object.assign({}, df);
    this.$input = makeInput(value || "");
    this.$wrapper = { is: () => true, removeClass() {} };
    this.required_calls = 0;
  }
  set_required() {
    this.required_calls += 1;
  }
  set_bold() {}
}

function makeFields(field_defs, doc) {
  const fields = {};
  for (const df of field_defs) {
    if (!df || !df.fieldname) continue;
    const value = doc[df.fieldname] || "";
    fields[df.fieldname] = new FakeField(df, value);
  }
  return fields;
}

class FakeAddressForm {
  constructor() {
    this.doctype = "Address";
    this.doc = { country: "Saudi Arabia" };
    this.dialog = this; // QuickEntryForm extends frappe.ui.Dialog
  }
  set_meta_and_mandatory_fields() {
    this.docfields = [
      { fieldname: "address_title", fieldtype: "Data", label: "Address Title" },
      { fieldname: "address_type", fieldtype: "Select", label: "Address Type" },
      { fieldname: "country", fieldtype: "Link", label: "Country", reqd: 1 },
      { fieldname: "pincode", fieldtype: "Data", label: "Postal Code", reqd: 1 },
    ];
  }
  render_dialog() {
    this.fields_dict = makeFields(this.docfields, this.doc);
    this.refresh_dependency = function () {
      for (const field of Object.values(this.fields_dict)) {
        const dep = field.df.mandatory_depends_on || "";
        if (dep.includes("country == 'India'")) {
          field.df.reqd = this.doc.country === "India" ? 1 : 0;
        } else if (dep) {
          // Approximates ERPNext's "address detail present" rules.
          field.df.reqd =
            this.doc.city || this.doc.country_address || this.doc.address_line1
              ? 1
              : 0;
        }
      }
    };
    this.refresh_dependency();
  }
}

class FakeIndiaAddressForm extends FakeAddressForm {
  get_address_fields() {
    const fields = [
      { fieldname: "address_line1", fieldtype: "Data", label: "Street Name" },
      { fieldname: "address_line2", fieldtype: "Data", label: "Building Number" },
      { fieldname: "_pincode", fieldtype: "Autocomplete", label: "Postal Code" },
      { fieldname: "city", fieldtype: "Data", label: "Subdivision Name" },
      { fieldname: "country", fieldtype: "Link", label: "Country" },
    ];
    const pincode = fields.find((f) => f.fieldname === "_pincode");
    pincode.mandatory_depends_on = "eval: doc.country == 'India'";
    return fields;
  }
  render_dialog() {
    this.docfields = this.get_address_fields();
    super.render_dialog();
  }
}

class FakeCustomerForm extends FakeAddressForm {
  set_meta_and_mandatory_fields() {
    this.docfields = [
      { fieldname: "customer_name", fieldtype: "Data", label: "Customer Name" },
      { fieldname: "customer_type", fieldtype: "Select", label: "Customer Type" },
      { fieldname: "custom_country", fieldtype: "Link", label: "Country" },
    ];
  }
  get_variant_fields() {
    return [
      { fieldname: "address_line1", fieldtype: "Data", label: "Address Line 1" },
      { fieldname: "address_line2", fieldtype: "Data", label: "Address Line 2" },
      { fieldname: "pincode", fieldtype: "Data", label: "ZIP Code" },
      { fieldname: "city", fieldtype: "Data", label: "City" },
      { fieldname: "state", fieldtype: "Data", label: "State/Province" },
      { fieldname: "country_address", fieldtype: "Link", label: "Country" },
    ];
  }
  render_dialog() {
    // Same as ERPNext's ContactAddressQuickEntryForm.
    this.docfields = this.docfields.concat(this.get_variant_fields());
    super.render_dialog();
  }
}

const context = {
  console,
  setTimeout: (fn) => {
    timers.push(fn);
    return timers.length;
  },
  document: {
    readyState: "loading",
    addEventListener(event, fn) {
      if (event === "DOMContentLoaded") dom_ready = fn;
    },
  },
  __: (text) => text,
  frappe: {
    provide() {},
    boot: {},
    model: {},
    call() {},
    ui: { form: {} },
    meta: {
      get_docfield(doctype, fieldname) {
        if (doctype !== "Address") return {};
        if (fieldname === "pincode") {
          return {
            fieldname: "pincode",
            fieldtype: "Data",
            label: "Postal Code",
            reqd: 1,
            mandatory_depends_on: "eval: doc.country == 'India'",
          };
        }
        return { fieldname, fieldtype: "Data", label: fieldname, reqd: 1 };
      },
      get_label(doctype, fieldname) {
        return fieldname;
      },
    },
  },
};
context.frappe.ui.form.on = () => {};
context.frappe.ui.form.ContactAddressQuickEntryForm = FakeCustomerForm;
context.frappe.ui.form.CustomerQuickEntryForm = FakeCustomerForm;

vm.createContext(context);
vm.runInContext(code, context, { filename: "customer_address.js" });
if (typeof dom_ready !== "function") {
  throw new Error("DOMContentLoaded listener was not registered");
}

context.frappe.ui.form.AddressQuickEntryForm = FakeAddressForm;
context.frappe.ui.form.SupplierQuickEntryForm = FakeAddressForm;
dom_ready();


function assert(cond, msg) {
  if (!cond) throw new Error("FAIL: " + msg);
}
function required(dialog, name) {
  return dialog.fields_dict[name] && dialog.fields_dict[name].df.reqd;
}

// 1. Base Address quick entry gains the five Saudi fields.
const base = new context.frappe.ui.form.AddressQuickEntryForm();
base.set_meta_and_mandatory_fields();
base.render_dialog();
for (const name of ["address_line1", "address_line2", "city", "county", "pincode"]) {
  assert(base.fields_dict[name], "base Address form is missing " + name);
}
assert(
  base.fields_dict.address_line1.df.label === "Street Name",
  "base Address street label should be normalized"
);
assert(
  base.fields_dict.address_line2.df.label === "Building Number",
  "base Address building label should be normalized"
);
assert(
  base.fields_dict.city.df.label === "Subdivision Name",
  "base Address city label should be normalized"
);
assert(
  base.fields_dict.county.df.label === "City Name",
  "base Address county label should be City Name"
);
assert(
  base.fields_dict.pincode.df.label === "Postal Code",
  "base Address pincode label should be normalized"
);
assert(required(base, "county") === 1, "Saudi county should be required");
assert(required(base, "address_line1") === 1, "Saudi address_line1 should be required");

// 2. Switch base form to UAE: no Saudi-only field stays mandatory.
base.doc.country = "United Arab Emirates";
base.fields_dict.country.$input._value = "United Arab Emirates";
base.refresh_dependency();
for (const name of ["address_line1", "address_line2", "city", "county", "pincode"]) {
  assert(
    !required(base, name),
    "UAE should not require " + name + " (got " + required(base, name) + ")"
  );
}

// 3. Switch back to Saudi Arabia: all five required again.
base.doc.country = "Saudi Arabia";
base.fields_dict.country.$input._value = "Saudi Arabia";
base.refresh_dependency();
for (const name of ["address_line1", "address_line2", "city", "county", "pincode"]) {
  assert(required(base, name) === 1, "Saudi should require " + name);
}

// 4. India Compliance style Address form: county is added, pincode alias used,
//    India's dependency stays intact outside Saudi Arabia.
context.frappe.ui.form.AddressQuickEntryForm = FakeIndiaAddressForm;
if (typeof context.zatca_wrap_quick_entry_form !== "function") {
  throw new Error("zatca_wrap_quick_entry_form is not a global function");
}
context.zatca_wrap_quick_entry_form("AddressQuickEntryForm");

const india = new context.frappe.ui.form.AddressQuickEntryForm();
india.doctype = "Address";
india.doc = { country: "India" };
india.set_meta_and_mandatory_fields();
india.render_dialog();
assert(india.fields_dict.county, "India Address form is missing county");
assert(india.fields_dict._pincode, "India Address form lost _pincode");
assert(!india.fields_dict.pincode, "India Address form should not duplicate pincode");
assert(required(india, "county") === 0, "India county should be optional");
assert(required(india, "_pincode") === 1, "India pincode dependency should be preserved");
assert(
  String(india.fields_dict._pincode.df.mandatory_depends_on || "").includes(
    "India"
  ),
  "India pincode dependency expression must be preserved"
);
assert(
  india.fields_dict._pincode.df.label === "Postal Code",
  "India _pincode label should be Postal Code"
);
assert(
  india.fields_dict.city.df.label === "Subdivision Name",
  "India city label should be normalized"
);

india.doc.country = "Saudi Arabia";
india.fields_dict.country.$input._value = "Saudi Arabia";
india.refresh_dependency();
assert(required(india, "county") === 1, "Saudi county should be required");
assert(required(india, "_pincode") === 1, "Saudi pincode should be required");

india.doc.country = "United Arab Emirates";
india.fields_dict.country.$input._value = "United Arab Emirates";
india.refresh_dependency();
assert(required(india, "county") === 0, "UAE county should be optional");
assert(required(india, "_pincode") === 0, "UAE pincode should be optional");

console.log("All quick-entry address checks passed.");

// 5. ERPNext ContactAddressQuickEntryForm style variant list: county appended,
//    country_address drives the requirement.
class FakeContactAddressForm extends FakeAddressForm {
  get_variant_fields() {
    return [
      {
        fieldname: "address_line1",
        fieldtype: "Data",
        label: "Address Line 1",
        mandatory_depends_on: "eval:doc.city || doc.country_address",
      },
      { fieldname: "address_line2", fieldtype: "Data", label: "Address Line 2" },
      { fieldname: "pincode", fieldtype: "Data", label: "ZIP Code" },
      {
        fieldname: "city",
        fieldtype: "Data",
        label: "City",
        mandatory_depends_on: "eval:doc.country_address || doc.address_line1",
      },
      { fieldname: "state", fieldtype: "Data", label: "State/Province" },
      {
        fieldname: "country_address",
        fieldtype: "Link",
        label: "Country",
        mandatory_depends_on: "eval:doc.city || doc.address_line1",
      },
    ];
  }
  render_dialog() {
    this.docfields = this.docfields.concat(this.get_variant_fields());
    super.render_dialog();
  }
}

context.frappe.ui.form.SupplierQuickEntryForm = FakeContactAddressForm;
context.zatca_wrap_quick_entry_form("SupplierQuickEntryForm");

const supplier = new context.frappe.ui.form.SupplierQuickEntryForm();
supplier.doctype = "Supplier";
supplier.doc = { country_address: "Saudi Arabia" };
supplier.set_meta_and_mandatory_fields();
supplier.render_dialog();
assert(supplier.fields_dict.county, "Supplier form is missing county");
assert(
  supplier.fields_dict.address_line1.df.label === "Street Name",
  "supplier street label should be normalized"
);
assert(
  supplier.fields_dict.address_line2.df.label === "Building Number",
  "supplier building label should be normalized"
);
assert(
  supplier.fields_dict.pincode.df.label === "Postal Code",
  "supplier pincode label should be normalized"
);
assert(
  supplier.fields_dict.city.df.label === "Subdivision Name",
  "supplier city label should be normalized"
);
assert(required(supplier, "county") === 1, "Saudi supplier county should be required");
assert(
  required(supplier, "address_line1") === 1,
  "Saudi supplier street should be required"
);
assert(
  !supplier.fields_dict.address_line1.df.mandatory_depends_on &&
    !supplier.fields_dict.city.df.mandatory_depends_on,
  "ERPNext address dependencies must not override the Saudi country rule"
);

// Simulate a Saudi address whose street/city were already filled in, then a
// change of country. The base form's "address detail present" rules must not
// keep Street / Subdivision required for a non-Saudi address.
supplier.doc.address_line1 = "King Fahd Road";
supplier.doc.city = "Al Olaya";
supplier.doc.country_address = "United Arab Emirates";
supplier.fields_dict.country_address.$input._value = "United Arab Emirates";
supplier.refresh_dependency();
assert(required(supplier, "county") === 0, "UAE supplier county should be optional");
assert(
  required(supplier, "address_line1") === 0,
  "UAE supplier street should be optional"
);
assert(required(supplier, "city") === 0, "UAE supplier city should be optional");
assert(
  required(supplier, "address_line2") === 0,
  "UAE supplier building should be optional"
);
assert(
  required(supplier, "pincode") === 0,
  "UAE supplier pincode should be optional"
);

console.log("All supplier quick-entry checks passed.");

// 6. ZATCA Customer shortcut form: visible custom_country, hidden
//    country_address, county inserted by the existing subclass, and the
//    wrapper's requirements applied on top.
const customer = new context.frappe.ui.form.CustomerQuickEntryForm();
customer.doctype = "Customer";
customer.doc = { custom_country: "Saudi Arabia" };
customer.set_meta_and_mandatory_fields();
customer.render_dialog();

assert(customer.fields_dict.custom_country, "ZATCA customer form lost custom_country");
assert(customer.fields_dict.county, "ZATCA customer form is missing county");
assert(
  customer.fields_dict.county.df.label === "City Name",
  "ZATCA customer county label should be City Name"
);
assert(
  customer.fields_dict.city.df.label === "Subdivision Name",
  "ZATCA customer city label should be Subdivision Name"
);
assert(
  customer.fields_dict.country_address.df.reqd === 0,
  "hidden country_address must not be required"
);
for (const name of ["address_line1", "address_line2", "city", "county", "pincode"]) {
  assert(required(customer, name) === 1, "Saudi customer should require " + name);
}
assert(
  customer.fields_dict.custom_country.df.mandatory_depends_on,
  "visible custom_country should keep the address requirement"
);

customer.doc.custom_country = "United Arab Emirates";
customer.fields_dict.custom_country.$input._value = "United Arab Emirates";
customer.refresh_dependency();
for (const name of ["address_line1", "address_line2", "city", "county", "pincode"]) {
  assert(
    !required(customer, name),
    "UAE customer should not require " + name
  );
}
assert(
  customer.flags_dict === undefined || !customer.fields_dict.country_address.df.reqd,
  "hidden country_address must stay optional for UAE"
);

console.log("All ZATCA customer quick-entry checks passed.");

// 7. Wrapping twice must not replace an already wrapped class.
const wrapped_supplier = context.frappe.ui.form.SupplierQuickEntryForm;
const wrapped_customer = context.frappe.ui.form.CustomerQuickEntryForm;
context.zatca_wrap_quick_entry_form("SupplierQuickEntryForm");
context.zatca_wrap_quick_entry_form("CustomerQuickEntryForm");
assert(
  context.frappe.ui.form.SupplierQuickEntryForm === wrapped_supplier,
  "supplier quick entry was wrapped twice"
);
assert(
  context.frappe.ui.form.CustomerQuickEntryForm === wrapped_customer,
  "customer quick entry was wrapped twice"
);

console.log("All quick-entry install checks passed.");

// 8. The requirement handler must never write to frappe.meta's docfields: the
//    same df objects are reused by the full Address form, so a Saudi quick
//    entry would otherwise leave "Postal Code is required" behind.
const meta_docfields = {
  address_line1: { fieldname: "address_line1", fieldtype: "Data", label: "Street Name", reqd: 0 },
  address_line2: {
    fieldname: "address_line2",
    fieldtype: "Data",
    label: "Building Number",
    reqd: 0,
  },
  city: { fieldname: "city", fieldtype: "Data", label: "Subdivision Name", reqd: 0 },
  county: { fieldname: "county", fieldtype: "Data", label: "City Name", reqd: 0 },
  pincode: { fieldname: "pincode", fieldtype: "Data", label: "Postal Code", reqd: 0 },
};
const meta_snapshot = JSON.stringify(meta_docfields);

// The normalizer must copy even when neither the label nor the dependency
// needs changing (pincode is the common case).
const raw_pincode = {
  fieldname: "pincode",
  fieldtype: "Data",
  label: "Postal Code",
  reqd: 0,
  mandatory_depends_on: "eval: doc.country == 'India'",
};
const [normalized_pincode] = context.zatca_normalize_quick_entry_address_labels([raw_pincode]);
assert(normalized_pincode !== raw_pincode, "normalizer must copy national-address docfields");
assert(
  normalized_pincode.mandatory_depends_on === raw_pincode.mandatory_depends_on,
  "India pincode dependency must be preserved on the copy"
);
normalized_pincode.reqd = 1;
assert(raw_pincode.reqd === 0, "writing reqd on the copy must not touch the source df");


class FakeMetaAddressForm extends FakeAddressForm {
  set_meta_and_mandatory_fields() {
    this.docfields = [
      { fieldname: "address_title", fieldtype: "Data", label: "Address Title" },
      { fieldname: "country", fieldtype: "Link", label: "Country", reqd: 1 },
    ].concat(Object.values(meta_docfields));
  }
  // Base QuickEntryForm keeps the meta objects themselves.
  render_dialog() {
    this.fields_dict = {};
    for (const df of this.docfields) {
      if (df.fieldname) this.fields_dict[df.fieldname] = new FakeField(df, "");
    }
    this.refresh_dependency = () => {};
    this.refresh_dependency();
  }
}

context.frappe.ui.form.AddressQuickEntryForm = FakeMetaAddressForm;
context.zatca_wrap_quick_entry_form("AddressQuickEntryForm");

const meta_form = new context.frappe.ui.form.AddressQuickEntryForm();
meta_form.doc = { country: "Saudi Arabia" };
meta_form.set_meta_and_mandatory_fields();
meta_form.render_dialog();

for (const name of ["address_line1", "address_line2", "city", "county", "pincode"]) {
  assert(required(meta_form, name) === 1, "Saudi meta form should require " + name);
}
assert(
  JSON.stringify(meta_docfields) === meta_snapshot,
  "quick entry must not mutate frappe.meta Address docfields (got " +
    JSON.stringify(meta_docfields) +
    ")"
);

console.log("All frappe.meta isolation checks passed.");
