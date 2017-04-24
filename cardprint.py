import argparse
from bitmerchant.wallet import Wallet
import cStringIO
import cups
import ethereum.keys
from mnemonic import Mnemonic
import os
from PIL import Image
import pystache
from reportlab.pdfgen import canvas
from reportlab.lib import units
from reportlab.lib.utils import ImageReader
from web3.main import to_checksum_address
import qrencode
import yaml


CARD_WIDTH = 54 * units.mm
CARD_HEIGHT = 85 * units.mm


def _addressFromWallet(wallet):
    return to_checksum_address(ethereum.keys.sha3(wallet.public_key.get_key().decode('hex')[1:])[12:].encode('hex'))


class BIPWallet(object):
    @classmethod
    def from_seed(cls, seed):
        return cls(Wallet.from_master_secret(seed))

    def __init__(self, wallet, derived=False):
        self.wallet = wallet
        self.derived = derived

    @property
    def derive(self):
        return BIPWallet(self.wallet, True)

    def address(self):
        if self.derived:
            def deriver(path):
                return _addressFromWallet(self.wallet.get_child_for_path(path))
            return deriver
        else:
            return _addressFromWallet(self.wallet)

    def pubkey(self):
        if self.derived:
            def deriver(path):
                return self.wallet.get_child_for_path(path).public_key.get_key()
            return deriver
        else:
            return self.wallet.public_key.get_key()

    def privkey(self):
        if self.derived:
            def deriver(path):
                return self.wallet.get_child_for_path(path).private_key.get_key()
            return deriver
        else:
            return self.wallet.private_key.get_key()


mnemonic = Mnemonic('english')

parser = argparse.ArgumentParser(description='Generate and print ECDSA keypairs.')
parser.add_argument('--printer', type=str, help='Printer name', default='EVOLIS_Primacy')
parser.add_argument('--test', type=str, help='Run in test mode, outputting to the named file')
parser.add_argument('--batchsize', type=int, help='Batch size for print jobs', default=None)
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
        pdata = os.urandom(16)
        pdata = chr(ord(pdata[0]) & 0x7F) + pdata[1:]
        words = mnemonic.to_mnemonic(pdata)
        seed = mnemonic.to_seed(words)
        privkey = seed[:32]
        address = ethereum.keys.privtoaddr(privkey).encode('hex')

        return {
            'keyphrase': words,
            'wallet': BIPWallet.from_seed(seed),
        }

    def generate(self, count):
        data = cStringIO.StringIO()
        c = canvas.Canvas(data, pagesize=(CARD_WIDTH, CARD_HEIGHT))

        addresses = []
        for i in range(count):
            c.rotate(90)

            context = self._makeKeypair()
            context['address'] = pystache.render(self.format['address'], context)
            addresses.append(context['address'])
            for element in self.format['card']:
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
        pystache.render(element['text'], context),
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
        pystache.render(element['text'], context))


@CardPrinter.formatter
def textArray(c, element, context):
    data = pystache.render(element['text'], context).split(element['split'])
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
    generator = CardPrinter(formatter)

    batchsize = args.batchsize or args.count
    for i in range(0, args.count, batchsize):
        count = min(batchsize, args.count - i)

        addresses, cards = generator.generate(count)
        print '\n'.join(addresses)
        if args.test:
            open(args.test, 'w').write(cards)
        else:
            printCards(args.printer, cards)


if __name__ == '__main__':
    args = parser.parse_args()
    main(args)
