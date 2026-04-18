(function (root, factory) {
    const api = factory();
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = api;
    }
    root.StreamDedup = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
    const THINK_CLOSE_MARKERS = ['</think>', '</thought>'];

    function stripLeakedThinkText(textChunk) {
        if (!textChunk) {
            return { content: '', hadLeak: false };
        }

        const lowered = textChunk.toLowerCase();
        let markerPos = -1;
        let markerLength = 0;

        for (const marker of THINK_CLOSE_MARKERS) {
            const pos = lowered.lastIndexOf(marker);
            if (pos > markerPos) {
                markerPos = pos;
                markerLength = marker.length;
            }
        }

        if (markerPos < 0) {
            return { content: textChunk, hadLeak: false };
        }

        return {
            content: textChunk.slice(markerPos + markerLength).trimStart(),
            hadLeak: true,
        };
    }

    function trimTextChunkAfterThoughtOverlap(textChunk, thoughtContent, isFirstTextChunk) {
        if (!textChunk || !thoughtContent || !isFirstTextChunk) {
            return textChunk;
        }

        const scanBase = thoughtContent.slice(-800);
        const overlapLen = Math.min(scanBase.length, textChunk.length);
        let maxOverlap = 0;

        for (let i = 6; i <= overlapLen; i++) {
            if (scanBase.endsWith(textChunk.slice(0, i))) {
                maxOverlap = i;
            }
        }

        return textChunk.slice(maxOverlap);
    }

    return {
        stripLeakedThinkText,
        trimTextChunkAfterThoughtOverlap,
    };
});
