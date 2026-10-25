frappe.ui.form.on("Zatca CSR Settings", {
	refresh(frm) {
		// The seller City Name (cbc:CityName) must be a Saudi National Address
		// city, so offer the official list while it is typed.
		frappe.zatca.saudi_city.attach(frm, "city_name");
	},

	city_name(frm) {
		frappe.zatca.saudi_city.attach(frm, "city_name");
	},
});
