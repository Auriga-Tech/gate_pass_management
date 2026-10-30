frappe.provide("gatepass");

gatepass.STATUS_COLOURS = {
	Draft: "gray", "At Gate": "orange", Inside: "blue",
	"Partially Processed": "yellow", Completed: "green",
	"Pending Return": "orange", "Partially Returned": "yellow",
	Returned: "green", "Overdue Return": "red", Closed: "green", Cancelled: "red",
};
