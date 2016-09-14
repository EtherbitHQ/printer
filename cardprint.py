import argparse
import cStringIO
import cups
import ethereum.keys
from mnemonic import Mnemonic
import os
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib import units
from reportlab.lib.utils import ImageReader
from web3.utils.address import to_checksum_address
import qrencode
import yaml


CARD_WIDTH = 54 * units.mm
CARD_HEIGHT = 85 * units.mm

mnemonic = Mnemonic('english')

parser = argparse.ArgumentParser(description='Generate and print ECDSA keypairs.')
parser.add_argument('--printer', type=str, help='Printer name', default='EVOLIS_Primacy')
parser.add_argument('--test', type=str, help='Run in test mode, outputting to the named file')
parser.add_argument('template', metavar='FILENAME', type=str, help='Template file to use')
parser.add_argument('count', metavar='COUNT', type=int, help='Number of cards to print')


class CardPrinter(object):
    FORMATTERS = {}

    @classmethod
    def formatter(cls, fun):
        cls.FORMATTERS[fun.__name__] = fun
        return fun

    def __init__(self, format):
        self.format = format

    def _makeKeypair(self):
        pdata = '\0' + os.urandom(15)
        words = mnemonic.to_mnemonic(pdata)
        privkey = mnemonic.to_seed(words)[:32]
        address = to_checksum_address(ethereum.keys.privtoaddr(privkey).encode('hex'))

        return {
            'keyphrase': words,
            'private': privkey.encode('hex'),
            'address': address,
        }

    def generate(self, count):
        data = cStringIO.StringIO()
        c = canvas.Canvas(data, pagesize=(CARD_WIDTH, CARD_HEIGHT))

        addresses = []
        for i in range(count):
            c.rotate(90)

            context = self._makeKeypair()
            addresses.append(context['address'])
            for element in self.format:
                self.FORMATTERS[element['type']](c, element, context)

            c.showPage()

        c.save()
        return addresses, data.getvalue()


@CardPrinter.formatter
def QR(c, element, context):
    eclevel = {
        'L': qrencode.QR_ECLEVEL_L,
        'M': qrencode.QR_ECLEVEL_M,
        'Q': qrencode.QR_ECLEVEL_Q,
        'H': qrencode.QR_ECLEVEL_H
    }[element.get('eclevel', 'L')]

    version, pixels, qr = qrencode.encode(
        element['text'] % context,
        0,
        eclevel,
        qrencode.QR_MODE_8,
        element.get('caseSensitive', True))
    qr = qr.resize((pixels * 64, pixels * 64), Image.NEAREST)
    size = element['size'] * units.mm
    c.drawImage(
        ImageReader(qr),
        float(element['x']) * units.mm,
        -float(element['y']) * units.mm - size,
        size, 
        size)


def drawText(c, element, x, y, data):
    text = c.beginText()
    text.setTextOrigin(x, y)
    text.setFont(element.get('font', 'Courier'), int(element.get('size', 12)))
    text.setLeading(float(element.get('leading', 12)))
    text.textLine(data)
    c.drawText(text)


@CardPrinter.formatter
def text(c, element, context):
    drawText(
        c,
        element,
        float(element['x']) * units.mm,
        -float(element['y']) * units.mm,
        element['text'] % context)


@CardPrinter.formatter
def textArray(c, element, context):
    data = (element['text'] % context).split(element['split'])
    cols = int(element['columns'])
    startX = float(element['x']) * units.mm
    startY = -float(element['y']) * units.mm
    colspacing = float(element['columnSpacing']) * units.mm
    rowspacing = -float(element['rowSpacing']) * units.mm

    for i in range(len(data)):
        drawText(c, element, startX + colspacing * (i % cols), startY + rowspacing * (i / cols), data[i])


def printCards(printerName, cards):
    conn = cups.Connection()
    job = conn.createJob(printerName, 'ether.cards', {'GRibbonType': 'RM_KBLACK'})
    conn.startDocument(printerName, job, 'card.pdf', 'application/pdf', 1)
    conn.writeRequestData(cards, len(cards))
    conn.finishDocument(printerName)


def main(args):
    formatter = yaml.load(open(args.template))
    generator = CardPrinter(formatter['card'])
    addresses, cards = generator.generate(args.count)
    print '\n'.join(addresses)
    if args.test:
        open(args.test, 'w').write(cards)
    else:
        printCards(args.printer, cards)


if __name__ == '__main__':
    args = parser.parse_args()
    main(args)
