/**
 * PDF Export Service
 * Handles exporting conversation to PDF
 * Charts appear naturally in conversation flow (between query and response)
 * Uses cloned element to avoid UI changes during export
 */
import html2canvas from 'html2canvas';
import jsPDF from 'jspdf';

export interface ExportOptions {
  conversationElementId: string;
  chartElementId?: string;
  filename?: string;
}

/**
 * Export conversation to PDF
 * Charts are included in natural conversation flow
 */
export async function exportToPdf(options: ExportOptions): Promise<boolean> {
  const {
    conversationElementId,
    filename = `conversation-${Date.now()}.pdf`
  } = options;

  try {
    const pdf = new jsPDF('p', 'mm', 'a4');
    const pageWidth = pdf.internal.pageSize.getWidth();
    const pageHeight = pdf.internal.pageSize.getHeight();
    const margin = 10;
    const contentWidth = pageWidth - (margin * 2);
    const contentHeight = pageHeight - (margin * 2);

    // Add header on first page
    pdf.setFontSize(16);
    pdf.text('Agentic Search Conversation', margin, margin + 5);
    pdf.setFontSize(10);
    pdf.text(`Exported: ${new Date().toLocaleString()}`, margin, margin + 12);

    let yOffset = margin + 20; // Start after header
    let currentPage = 0;

    // Capture conversation (charts included naturally)
    const conversationElement = document.getElementById(conversationElementId);
    if (conversationElement) {
      // Clone the element to avoid modifying the visible UI
      const clone = conversationElement.cloneNode(true) as HTMLElement;

      // Style the clone to be off-screen but rendered
      clone.style.position = 'absolute';
      clone.style.left = '-9999px';
      clone.style.top = '0';
      clone.style.width = `${conversationElement.offsetWidth}px`;
      clone.style.backgroundColor = '#ffffff';

      // Append clone to body for rendering
      document.body.appendChild(clone);

      // Copy canvas content from original to clone (Chart.js renders to canvas)
      const originalCanvases = conversationElement.querySelectorAll('canvas');
      const clonedCanvases = clone.querySelectorAll('canvas');
      originalCanvases.forEach((originalCanvas, index) => {
        if (clonedCanvases[index]) {
          const clonedCanvas = clonedCanvases[index] as HTMLCanvasElement;
          const ctx = clonedCanvas.getContext('2d');
          if (ctx) {
            // Match dimensions
            clonedCanvas.width = originalCanvas.width;
            clonedCanvas.height = originalCanvas.height;
            // Copy the drawn content
            ctx.drawImage(originalCanvas, 0, 0);
          }
        }
      });

      // Hide agent thinking sections and tabs in the clone
      const thinkingSections = clone.querySelectorAll('.processing-chain');
      const tabSections = clone.querySelectorAll('.conversation-tabs');

      thinkingSections.forEach((el) => {
        (el as HTMLElement).style.display = 'none';
      });
      tabSections.forEach((el) => {
        (el as HTMLElement).style.display = 'none';
      });

      // Expand all chart containers in the clone to show all charts
      const chartContainers = clone.querySelectorAll('#chart-container');
      chartContainers.forEach((el) => {
        const htmlEl = el as HTMLElement;
        htmlEl.style.overflow = 'visible';
        htmlEl.style.overflowX = 'visible';
        htmlEl.style.width = 'auto';
      });

      // Small delay for reflow
      await new Promise(resolve => setTimeout(resolve, 100));

      const conversationCanvas = await html2canvas(clone, {
        scale: 2,
        useCORS: true,
        logging: false,
        backgroundColor: '#ffffff',
        windowHeight: clone.scrollHeight,
        height: clone.scrollHeight
      });

      // Remove the clone from DOM
      document.body.removeChild(clone);

      // Calculate dimensions
      const imgWidth = contentWidth;
      const ratio = imgWidth / conversationCanvas.width;

      // Add padding at page breaks to reduce text cutting (15mm safe zone)
      const pageBreakPadding = 15;

      // Calculate page heights with padding
      const firstPageContentHeight = contentHeight - 20 - pageBreakPadding;
      const firstPageCanvasHeight = firstPageContentHeight / ratio;
      const regularPageContentHeight = contentHeight - pageBreakPadding;
      const regularPageCanvasHeight = regularPageContentHeight / ratio;

      let sourceY = 0;
      let remainingCanvasHeight = conversationCanvas.height;

      while (remainingCanvasHeight > 0) {
        const pageCanvasHeight = currentPage === 0 ? firstPageCanvasHeight : regularPageCanvasHeight;
        const sliceHeight = Math.min(remainingCanvasHeight, pageCanvasHeight);

        if (currentPage > 0) {
          pdf.addPage();
          yOffset = margin;
        }

        // Create a temporary canvas for this slice
        const sliceCanvas = document.createElement('canvas');
        sliceCanvas.width = conversationCanvas.width;
        sliceCanvas.height = sliceHeight;
        const ctx = sliceCanvas.getContext('2d');

        if (ctx) {
          ctx.drawImage(
            conversationCanvas,
            0, sourceY, conversationCanvas.width, sliceHeight,
            0, 0, conversationCanvas.width, sliceHeight
          );

          const sliceImg = sliceCanvas.toDataURL('image/png');
          const sliceImgHeight = sliceHeight * ratio;

          pdf.addImage(
            sliceImg,
            'PNG',
            margin,
            yOffset,
            imgWidth,
            sliceImgHeight,
            undefined,
            'FAST'
          );

          yOffset += sliceImgHeight;
        }

        sourceY += sliceHeight;
        remainingCanvasHeight -= sliceHeight;
        currentPage++;
      }
    }

    // Save PDF
    pdf.save(filename);
    return true;

  } catch (error) {
    console.error('Error exporting PDF:', error);
    return false;
  }
}

/**
 * Check if chart is visible in DOM
 */
export function isChartVisible(chartElementId: string = 'chart-container'): boolean {
  const chartElement = document.getElementById(chartElementId);
  return chartElement !== null && chartElement.offsetParent !== null;
}
