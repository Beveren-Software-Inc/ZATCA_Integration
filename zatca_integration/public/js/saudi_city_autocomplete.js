// City Name (cbc:CityName) type-ahead for Saudi addresses.
//
// ZATCA only accepts a city of the Saudi National Address database, and any
// other value is reported as "Inaccurate Seller/Buyer Address Data". Waiting for
// the save-time error is late, so the official list is offered while the user
// types - the value stored is always the official spelling.
frappe.provide("frappe.zatca");
frappe.provide("frappe.zatca.saudi_city");

frappe.zatca.saudi_city.options = null;
frappe.zatca.saudi_city._loading = false;
frappe.zatca.saudi_city._waiters = [];

frappe.zatca.saudi_city.is_saudi = function (country) {
	const value = String(country || "")
		.trim()
		.toLowerCase();
	return value === "saudi arabia" || value === "sa" || value === "ksa";
};

// The list is fetched once per page session and shared by every form.
frappe.zatca.saudi_city.load = function (callback) {
	if (frappe.zatca.saudi_city.options) {
		callback(frappe.zatca.saudi_city.options);
		return;
	}

	frappe.zatca.saudi_city._waiters.push(callback);
	if (frappe.zatca.saudi_city._loading) {
		return;
	}

	frappe.zatca.saudi_city._loading = true;
	frappe.call({
		method: "zatca_integration.overrides.address.get_saudi_city_options",
		callback(r) {
			frappe.zatca.saudi_city.options = r.message || [];
			frappe.zatca.saudi_city.flush();
		},
		error() {
			// Never block the form: the server still validates on save.
			frappe.zatca.saudi_city.options = [];
			frappe.zatca.saudi_city.flush();
		},
	});
};

frappe.zatca.saudi_city.flush = function () {
	frappe.zatca.saudi_city._loading = false;
	const waiters = frappe.zatca.saudi_city._waiters || [];
	frappe.zatca.saudi_city._waiters = [];
	waiters.forEach((callback) => callback(frappe.zatca.saudi_city.options));
};

// 3 = the name starts with the typed text, 2 = a word of it does, 1 = it is
// contained, 0 = no match. English and Arabic are both searched.
frappe.zatca.saudi_city.score = function (query, option) {
	const needle = String(query || "")
		.trim()
		.toLowerCase();
	if (!needle) {
		return 0;
	}

	const words = [option.value, option.arabic]
		.filter(Boolean)
		.map((value) => String(value).toLowerCase());
	let best = 0;
	words.forEach((word) => {
		if (word.startsWith(needle)) {
			best = Math.max(best, 3);
		} else if (word.split(/[\s\-'’]+/).some((part) => part.startsWith(needle))) {
			best = Math.max(best, 2);
		} else if (word.includes(needle)) {
			best = Math.max(best, 1);
		}
	});
	return best;
};

frappe.zatca.saudi_city.widget = function (input) {
	if (input.zatca_saudi_city_widget) {
		return input.zatca_saudi_city_widget;
	}

	let mapped_for = null;
	let mapped = new Map();
	const option_for = (value) => {
		const list = frappe.zatca.saudi_city.options || [];
		if (mapped_for !== list) {
			mapped = new Map(list.map((option) => [option.value, option]));
			mapped_for = list;
		}
		return mapped.get(value);
	};

	const widget = new Awesomplete(input, {
		// 0 keeps the list available when an existing name is clicked into; an
		// empty field stays quiet until something is typed.
		minChars: 0,
		maxItems: 10,
		autoFirst: false,
		list: [],
		data: (item) => item,
		filter(item, query) {
			const option = option_for(item.value) || { value: item.value };
			item.zatca_score = frappe.zatca.saudi_city.score(query, option);
			return item.zatca_score > 0;
		},
		sort(a, b) {
			return (
				(b.zatca_score || 0) - (a.zatca_score || 0) ||
				String(a.value).localeCompare(String(b.value))
			);
		},
		item(item) {
			const option = option_for(item.value) || {};
			const city = frappe.utils.escape_html(option.value || item.value);
			const hint = [option.region, option.arabic]
				.filter(Boolean)
				.map((part) => frappe.utils.escape_html(part))
				.join(" · ");
			const li = document.createElement("li");
			li.setAttribute("aria-selected", "false");
			// One line: the list item is ellipsised, and the region plus the
			// Arabic name tells two same-sounding cities apart.
			li.innerHTML = `<strong>${city}</strong>${
				hint ? ` <span class="text-muted small">${hint}</span>` : ""
			}`;
			return li;
		},
	});

	input.zatca_saudi_city_widget = widget;

	// Awesomplete writes the picked name straight into the input, which a Data
	// field does not notice on its own (Frappe's Autocomplete control wires the
	// same event), so the form value is updated the moment a city is picked.
	$(input).on("awesomplete-selectcomplete", () => {
		$(input).trigger("change");
	});

	return widget;
};

// Attach (or refresh) the type-ahead on the City Name field. ``form`` is a
// Frappe form or a quick entry dialog - both expose ``fields_dict``.
frappe.zatca.saudi_city.attach = function (form, fieldname = "county") {
	if (!form || !form.fields_dict || !window.Awesomplete) {
		return;
	}

	const field = form.fields_dict[fieldname];
	const input = field && field.$input && field.$input.get(0);
	if (!input) {
		return;
	}

	const widget = frappe.zatca.saudi_city.widget(input);
	if (!frappe.zatca.saudi_city.is_saudi(form.doc && form.doc.country)) {
		// A foreign address keeps whatever city name its own country uses.
		widget.list = [];
		return;
	}

	if (frappe.zatca.saudi_city.options) {
		widget.list = frappe.zatca.saudi_city.options;
		return;
	}

	// Re-attach once the list arrives, so a country that changed in the meantime
	// is respected.
	frappe.zatca.saudi_city.load(() => frappe.zatca.saudi_city.attach(form, fieldname));
};
