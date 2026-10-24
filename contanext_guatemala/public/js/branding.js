(() => {
	const upstreamName = /ERP\s*Next/gi;
	const brandMark = "/assets/contanext_guatemala/images/contanext-mark.svg";
	const excludedSelector = "input, textarea, pre, code, script, style, noscript, template, [contenteditable='true']";
	const visibleAttributes = ["aria-label", "alt", "placeholder", "title"];

	function branded(value) {
		return value?.replace(upstreamName, "ContaNext");
	}

	function brandElement(element) {
		if (element.closest(excludedSelector)) return;

		if (element instanceof HTMLImageElement && /\/assets\/erpnext\/images\/erpnext-logo\.svg(?:\?.*)?$/.test(element.src)) {
			element.src = brandMark;
		}
		if (element instanceof HTMLLinkElement && element.relList.contains("icon") && /erpnext-favicon\.svg(?:\?.*)?$/.test(element.href)) {
			element.href = brandMark;
		}

		for (const attribute of visibleAttributes) {
			const value = element.getAttribute(attribute);
			if (value && upstreamName.test(value)) element.setAttribute(attribute, branded(value));
			upstreamName.lastIndex = 0;
		}
	}

	function replaceText(root) {
		if (root.nodeType === Node.TEXT_NODE) {
			if (!root.parentElement?.closest(excludedSelector) && upstreamName.test(root.nodeValue)) {
				root.nodeValue = branded(root.nodeValue);
			}
			upstreamName.lastIndex = 0;
			return;
		}

		if (!(root instanceof Element) || root.matches(excludedSelector)) return;
		brandElement(root);

		const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
		while (walker.nextNode()) {
			const node = walker.currentNode;
			if (node instanceof Element) brandElement(node);
			else replaceText(node);
		}
	}

	function applyBranding() {
		document.title = branded(document.title);
		replaceText(document.body);
	}

	function start() {
		applyBranding();
		new MutationObserver((mutations) => {
			for (const mutation of mutations) {
				if (mutation.type === "characterData" || mutation.type === "attributes") replaceText(mutation.target);
				for (const node of mutation.addedNodes) replaceText(node);
			}
		}).observe(document.documentElement, {
			attributes: true,
			attributeFilter: [...visibleAttributes, "href", "src"],
			childList: true,
			characterData: true,
			subtree: true,
		});
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", start, { once: true });
	} else {
		start();
	}
})();
