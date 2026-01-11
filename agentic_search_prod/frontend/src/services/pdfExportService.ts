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
    let yOffset = margin;

    // Add title
    pdf.setFontSize(16);
    pdf.text('Agentic Search Conversation', margin, yOffset);
    yOffset += 10;

    // Add timestamp
    pdf.setFontSize(10);
    pdf.text(`Exported: ${new Date().toLocaleString()}`, margin, yOffset);
    yOffset += 10;

    // Capture conversation
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
        backgroundColor: '#ffffff'
      });

      // Restore agent thinking sections and tabs after capture
      thinkingSections.forEach((el) => {
        (el as HTMLElement).style.display = '';
      });
      tabSections.forEach((el) => {
        (el as HTMLElement).style.display = '';
      });

      const conversationImg = conversationCanvas.toDataURL('image/png');
      const imgWidth = contentWidth;
      const imgHeight = (conversationCanvas.height * imgWidth) / conversationCanvas.width;

      // Handle multi-page for long conversations
      let remainingHeight = imgHeight;
      let sourceY = 0;

      while (remainingHeight > 0) {
        const availableHeight = pageHeight - yOffset - margin;
        const sliceHeight = Math.min(remainingHeight, availableHeight);
        const sliceRatio = sliceHeight / imgHeight;

        if (sourceY > 0) {
          pdf.addPage();
          yOffset = margin;
        }

        pdf.addImage(
          conversationImg,
          'PNG',
          margin,
          yOffset,
          imgWidth,
          sliceHeight,
          undefined,
          'FAST'
        );

        remainingHeight -= sliceHeight;
        sourceY += sliceRatio * conversationCanvas.height;
        yOffset += sliceHeight;
      }
    }

    // Capture chart if exists in DOM
    const chartElement = document.getElementById(chartElementId);
    if (chartElement && chartElement.offsetParent !== null) {
      pdf.addPage();
      yOffset = margin;

      pdf.setFontSize(14);
      pdf.text('Visualization', margin, yOffset);
      yOffset += 10;

      const chartCanvas = await html2canvas(chartElement, {
        scale: 2,
        useCORS: true,
        logging: false,
        backgroundColor: '#ffffff'
      });

      const chartImg = chartCanvas.toDataURL('image/png');
      const chartWidth = contentWidth;
      const chartHeight = (chartCanvas.height * chartWidth) / chartCanvas.width;

      pdf.addImage(
        chartImg,
        'PNG',
        margin,
        yOffset,
        chartWidth,
        Math.min(chartHeight, pageHeight - yOffset - margin),
        undefined,
        'FAST'
      );
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
