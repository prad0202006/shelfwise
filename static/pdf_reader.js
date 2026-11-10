(() => {
    const root = document.querySelector("#pdf-reader");
    if (!root || !window.pdfjsLib) return;

    const canvas = document.querySelector("#pdf-canvas");
    const context = canvas.getContext("2d");
    const status = document.querySelector("#reader-status");
    const pageInput = document.querySelector("#page-number");
    const pageCount = document.querySelector("#page-count");
    const zoomLabel = document.querySelector("#zoom-level");
    const stage = document.querySelector("#reader-stage");
    let documentProxy;
    let pageNumber = 1;
    let zoom = 1;
    let renderTask;
    let resizeTimer;

    window.pdfjsLib.GlobalWorkerOptions.workerSrc =
        "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";

    async function renderPage() {
        if (!documentProxy) return;
        if (renderTask) {
            renderTask.cancel();
            try {
                await renderTask.promise;
            } catch (error) {
                if (error.name !== "RenderingCancelledException") throw error;
            }
        }

        const page = await documentProxy.getPage(pageNumber);
        const naturalViewport = page.getViewport({ scale: 1 });
        const fitScale = Math.min((stage.clientWidth - 48) / naturalViewport.width, 1.4);
        const viewport = page.getViewport({ scale: Math.max(fitScale, 0.35) * zoom });
        const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);

        canvas.width = Math.floor(viewport.width * pixelRatio);
        canvas.height = Math.floor(viewport.height * pixelRatio);
        canvas.style.width = `${viewport.width}px`;
        canvas.style.height = `${viewport.height}px`;
        renderTask = page.render({
            canvasContext: context,
            viewport,
            transform: [pixelRatio, 0, 0, pixelRatio, 0, 0],
        });
        await renderTask.promise;
        renderTask = undefined;
        status.hidden = true;
        canvas.hidden = false;
        pageInput.value = pageNumber;
        zoomLabel.textContent = `${Math.round(zoom * 100)}%`;
        document.querySelector('[data-action="previous"]').disabled = pageNumber <= 1;
        document.querySelector('[data-action="next"]').disabled = pageNumber >= documentProxy.numPages;
    }

    function showError() {
        status.textContent = "This PDF could not be loaded. Check your connection and try again.";
        status.classList.add("is-error");
        canvas.hidden = true;
    }

    document.querySelectorAll("[data-action]").forEach(button => {
        button.addEventListener("click", () => {
            const action = button.dataset.action;
            if (action === "previous") pageNumber = Math.max(1, pageNumber - 1);
            if (action === "next") pageNumber = Math.min(documentProxy.numPages, pageNumber + 1);
            if (action === "zoom-in") zoom = Math.min(2.5, zoom + 0.15);
            if (action === "zoom-out") zoom = Math.max(0.55, zoom - 0.15);
            renderPage().catch(showError);
        });
    });

    pageInput.addEventListener("change", () => {
        const requestedPage = Number.parseInt(pageInput.value, 10);
        pageNumber = Math.min(documentProxy.numPages, Math.max(1, requestedPage || 1));
        renderPage().catch(showError);
    });

    window.addEventListener("resize", () => {
        window.clearTimeout(resizeTimer);
        resizeTimer = window.setTimeout(() => renderPage().catch(showError), 120);
    });

    window.pdfjsLib.getDocument(root.dataset.pdfUrl).promise
        .then(pdf => {
            documentProxy = pdf;
            pageCount.textContent = pdf.numPages;
            pageInput.max = pdf.numPages;
            pageInput.disabled = false;
            return renderPage();
        })
        .catch(showError);
})();