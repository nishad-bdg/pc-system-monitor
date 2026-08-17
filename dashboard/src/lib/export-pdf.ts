import type { jsPDF } from "jspdf";

export type PdfTable = {
  title: string;
  head: string[];
  body: string[][];
};

export type PdfStat = {
  label: string;
  value: string;
};

export type ExportPdfOptions = {
  filename: string;
  title: string;
  subtitle: string[];
  stats: PdfStat[];
  tables: PdfTable[];
};

function pdfText(value: string | number | null | undefined): string {
  return String(value ?? "-").replaceAll("—", "-");
}

function addFooter(doc: jsPDF, pageWidth: number, pageHeight: number) {
  const pageCount = doc.getNumberOfPages();
  for (let i = 1; i <= pageCount; i++) {
    doc.setPage(i);
    doc.setFontSize(8);
    doc.setTextColor(100);
    doc.text(`Page ${i} of ${pageCount}`, pageWidth - 40, pageHeight - 18, {
      align: "right",
    });
    doc.text("System Info Report", 40, pageHeight - 18);
  }
}

/** Build a landscape A4 PDF of the Report Export preview and trigger download. */
export async function downloadExportPdf(opts: ExportPdfOptions): Promise<void> {
  const { jsPDF } = await import("jspdf");
  const autoTable = (await import("jspdf-autotable")).default;

  const doc = new jsPDF({ orientation: "landscape", unit: "pt", format: "a4" });
  const pageWidth = doc.internal.pageSize.getWidth();
  const pageHeight = doc.internal.pageSize.getHeight();
  let y = 36;

  doc.setFont("helvetica", "bold");
  doc.setFontSize(16);
  doc.setTextColor(15, 23, 42);
  doc.text(opts.title, 40, y);
  y += 18;

  doc.setFont("helvetica", "normal");
  doc.setFontSize(9);
  doc.setTextColor(71, 85, 105);
  for (const line of opts.subtitle) {
    doc.text(pdfText(line), 40, y);
    y += 12;
  }
  y += 6;

  if (opts.stats.length > 0) {
    autoTable(doc, {
      startY: y,
      theme: "plain",
      styles: { fontSize: 9, cellPadding: 6 },
      columnStyles: {
        0: { cellWidth: (pageWidth - 80) / opts.stats.length },
      },
      body: [
        opts.stats.map((s) => `${s.label}\n${pdfText(s.value)}`),
      ],
      didParseCell: (data) => {
        if (data.section === "body") {
          data.cell.styles.fillColor = [241, 245, 249];
          data.cell.styles.textColor = [15, 23, 42];
        }
      },
      margin: { left: 40, right: 40 },
    });
    const withTable = doc as jsPDF & { lastAutoTable?: { finalY: number } };
    y = (withTable.lastAutoTable?.finalY ?? y) + 16;
  }

  for (const table of opts.tables) {
    if (table.body.length === 0) continue;
    if (y > pageHeight - 80) {
      doc.addPage();
      y = 36;
    }
    doc.setFont("helvetica", "bold");
    doc.setFontSize(11);
    doc.setTextColor(15, 23, 42);
    doc.text(table.title, 40, y);
    y += 8;
    autoTable(doc, {
      startY: y,
      head: [table.head.map(pdfText)],
      body: table.body.map((row) => row.map(pdfText)),
      theme: "grid",
      styles: {
        fontSize: 7,
        cellPadding: 3,
        overflow: "linebreak",
        valign: "middle",
        textColor: [51, 65, 85],
      },
      headStyles: {
        fillColor: [30, 41, 59],
        textColor: 255,
        fontStyle: "bold",
        fontSize: 7,
      },
      alternateRowStyles: { fillColor: [248, 250, 252] },
      margin: { left: 40, right: 40, bottom: 32 },
    });
    const withTable = doc as jsPDF & { lastAutoTable?: { finalY: number } };
    y = (withTable.lastAutoTable?.finalY ?? y) + 18;
  }

  addFooter(doc, pageWidth, pageHeight);
  doc.save(opts.filename);
}
