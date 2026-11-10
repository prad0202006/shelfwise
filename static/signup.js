document.querySelectorAll("#specialization[data-course-options]").forEach(select => {
    const form = select.closest("form");
    const courseSelect = form.querySelector("#course");
    const options = JSON.parse(select.dataset.courseOptions);
    const preferred = select.dataset.currentSpecialization || "";

    function updateSpecializations() {
        const selected = select.value || preferred;
        select.replaceChildren(new Option("Select specialization", ""));
        for (const specialization of options[courseSelect.value] || []) {
            select.add(new Option(specialization, specialization));
        }
        if ([...select.options].some(option => option.value === selected)) {
            select.value = selected;
        }
    }

    courseSelect.addEventListener("change", () => {
        select.dataset.currentSpecialization = "";
        updateSpecializations();
    });
    updateSpecializations();
});