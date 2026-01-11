/**
 * PDF Export Service
 * Handles exporting conversation and charts to PDF
 */
import html2canvas from 'html2canvas';
import jsPDF from 'jspdf';

export interface ExportOptions {
  conversationElementId: string;
  chartElementId?: string;
  filename?: string;
}

/**
 * Export conversation (and optionally chart) to PDF
 * Order: Header -> Chart (if visible) -> Conversation
 */
export async function exportToPdf(options: ExportOptions): Promise<boolean> {
  const {
    conversationElementId,
    chartElementId = 'chart-container',
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

    // 1. Capture chart first (if visible)
    const chartElement = document.getElementById(chartElementId);
    if (chartElement && chartElement.offsetParent !== null) {
      // Store original styles to restore later
      const originalOverflow = chartElement.style.overflow;
      const originalOverflowX = chartElement.style.overflowX;
      const originalWidth = chartElement.style.width;

      // Expand container to show all charts
      chartElement.style.overflow = 'visible';
      chartElement.style.overflowX = 'visible';
      chartElement.style.width = `${chartElement.scrollWidth}px`;

      await new Promise(resolve => setTimeout(resolve, 50));

      const chartCanvas = await html2canvas(chartElement, {
        scale: 2,
        useCORS: true,
        logging: false,
        backgroundColor: '#ffffff',
        width: chartElement.scrollWidth
      });

      // Restore original styles
      chartElement.style.overflow = originalOverflow;
      chartElement.style.overflowX = originalOverflowX;
      chartElement.style.width = originalWidth;

      if (chartCanvas.width > 0 && chartCanvas.height > 0) {
        const chartImg = chartCanvas.toDataURL('image/png');
        const chartWidth = contentWidth;
        const chartHeight = (chartCanvas.height * chartWidth) / chartCanvas.width;
        const maxChartHeight = contentHeight - yOffset - margin;

        pdf.addImage(
          chartImg,
          'PNG',
          margin,
          yOffset,
          chartWidth,
          Math.min(chartHeight, maxChartHeight),
          undefined,
          'FAST'
        );

        yOffset += Math.min(chartHeight, maxChartHeight) + 10; // Add spacing after chart
      }
    }

    // 2. Capture conversation
    const conversationElement = document.getElementById(conversationElementId);
    if (conversationElement) {
      // Hide agent thinking sections and tabs before capture
      const thinkingSections = conversationElement.querySelectorAll('.processing-chain');
      const tabSections = conversationElement.querySelectorAll('.conversation-tabs');

      thinkingSections.forEach((el) => {
        (el as HTMLElement).style.display = 'none';
      });
      tabSections.forEach((el) => {
        (el as HTMLElement).style.display = 'none';
      });

      const conversationCanvas = await html2canvas(conversationElement, {
        scale: 2,
        useCORS: true,
        logging: false,
        backgroundColor: '#ffffff',
        windowHeight: conversationElement.scrollHeight,
        height: conversationElement.scrollHeight
      });

      // Restore agent thinking sections and tabs after capture
      thinkingSections.forEach((el) => {
        (el as HTMLElement).style.display = '';
      });
      tabSections.forEach((el) => {
        (el as HTMLElement).style.display = '';
      });

      // Calculate dimensions
      const imgWidth = contentWidth;
      const ratio = imgWidth / conversationCanvas.width;

      // Calculate remaining space on first page after chart
      const firstPageRemainingHeight = contentHeight - yOffset + margin;
      const firstPageCanvasHeight = firstPageRemainingHeight / ratio;
      const regularPageCanvasHeight = contentHeight / ratio;

      let sourceY = 0;
      let remainingCanvasHeight = conversationCanvas.height;
      let isFirstConversationPage = true;

      while (remainingCanvasHeight > 0) {
        const pageCanvasHeight = isFirstConversationPage ? firstPageCanvasHeight : regularPageCanvasHeight;
        const sliceHeight = Math.min(remainingCanvasHeight, pageCanvasHeight);

        // Add new page if not first conversation segment
        if (!isFirstConversationPage) {
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
        }

        sourceY += sliceHeight;
        remainingCanvasHeight -= sliceHeight;
        isFirstConversationPage = false;
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
