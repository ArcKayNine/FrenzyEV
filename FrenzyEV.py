import copy
from random import shuffle
import matplotlib.pyplot as plt
import numpy as np
import pickle

class EndTurn(Exception): pass
class PassPriority(Exception): pass

# This class object holds all the info we need about each card.
class Card:
    def __init__(self, name, cmc, spectacleCmc, wizzCmc, cardType, castDamage, power, haste, isWizard, qtty):
        self.name = name
        self.cmc = cmc
        self.spectacleCmc = spectacleCmc
        self.wizzCmc = wizzCmc
        self.type = cardType
        self.castDamage = castDamage
        self.power = power #Base power
        self.haste = haste
        self.isWizard = isWizard
        self.qtty = qtty
        self.counters = 0

    def __str__(self):
        return self.name

    def canPlay(self, boardstate):
        # Given a boardstate, is this card instance castable?
        if self.type == 'land':
            if boardstate.lft:
                return False
            else:
                return True
        if self.currentCost(boardstate) <= boardstate.mana:
            return True
        else:
            return False

    def canPlayWSteamKin(self, boardstate, fullKins):
        # Given a boardstate, could we cast this card with the help of steamkin mana?
        # Returns [T/F, n], where n is the number of steamkins we need counters from.
        if self.type == 'land':
            if boardstate.lft:
                return [False,0]
            else:
                return [True,0]
                
        cCost = self.currentCost(boardstate)
        usedKins = 0
        mana = boardstate.mana
        while fullKins > 0 and cCost > mana:
            if cCost <= mana:
                break
            else:
                mana += 3
                usedKins += 1
                fullKins -= 1
        if cCost <= mana:
            return [True,usedKins]
        else:
            return [False,0]

    def currentCost(self, boardstate):
        costs = [self.cmc]
        for creature in boardstate.creatures:
            if creature.isWizard:
                costs.append(self.wizzCmc)
                break
        if boardstate.spectacle > 0:
            costs.append(self.spectacleCmc)
        return min(costs)
        
# This class holds the boardstate info.
# For ease of use, spectacle is damage dealt this turn.
# If it is 0, then Bool(self.spectacle) will be False.
class Boardstate:
    def __init__(self, library, lands=4, creatures=0):
        self.lands = lands
        self.mana = lands
        if not creatures:
            self.creatures = []
        else:
            self.creatures = creatures
        self.damage = 0
        self.spectacle = 0
        self.combat = 0
        self.lft = 0 # Land for turn
        self.lightCards = []
        self.lightTimer = []
        self.library = library

    def cast(self, card):
        # Play the card
        self.damage += card.castDamage

        # Calculate cost and adjust available mana
        self.mana -= card.currentCost(self)

        if card.type == 'land':
            self.lft = 1
            self.lands +=1
            self.mana +=1
        else:
            # Add steam kin counters
            for creature in self.creatures:
                if creature.name == 'SteamKin' and creature.counters < 3:
                    creature.counters += 1

        # Record creatures in play
        if card.type == 'creature':
            self.creatures.append(card)

        # Exile Light Up the Stage Cards
        # Doesn't execute this step if there are less than 2 cards below Light Up
        if card.name == 'LightUp' and len(self.library)>3:
            try:
                self.instantCastLoop(1)
            except PassPriority:
                pass
            self.lightCards.append(self.library.pop(1))
            self.lightCards.append(self.library.pop(1))
            self.lightTimer.append(2)
            self.lightTimer.append(2)

    def goToCombat(self, verb):
        # All creatures that can attack do so.
        if not self.combat:
            counter = 0
            for creature in self.creatures:
                if creature.haste:
                    self.damage    += creature.power + creature.counters
                    self.spectacle += creature.power + creature.counters
                    counter += creature.power + creature.counters
                    if verb:
                        print('{} attacking with {} power and {} +1/+1 counters'.format(creature, creature.power, creature.counters))
            self.combat = 1
            if verb:
                print('Total of {} damage dealt in combat'.format(counter))
        else:
            if verb:
                print('Oops, we\'ve already attacked...')

    def castLoop(self, verb=0):
        outstr = ''
        # Check if there are cards left:
        if len(self.library) == 0:
            raise EndTurn
        # Check if castable with SteamKin counters now, save info
        canPWK = self.library[0].canPlayWSteamKin(self, len([SK for SK in self.creatures if SK.name == 'SteamKin' and SK.counters == 3]))
        if len(self.lightCards) == 0:
            canPLUWK = [0]
        else:
            canPLUWK = [c.canPlayWSteamKin(self, len([SK for SK in self.creatures if SK.name == 'SteamKin' and SK.counters == 3]))[1] for c in self.lightCards]
        
        # Go to combat if we can cheapen the cost of a spectacle spell on top
        if self.library[0].spectacleCmc < self.library[0].cmc and not self.spectacle and sum([c.power+c.counters for c in self.creatures if c.haste]) > 0:
            outstr += 'Going to combat\n'
            self.goToCombat(verb)

        # If castable, cast
        elif self.library[0].canPlay(self):
            self.cast(self.library[0])
            outstr += '{} cast (now {} mana)\n'.format(self.library.pop(0), self.mana)

        # If castable with SteamKin counters, attack w SteamKin (or not if Main 2), then make mana
        elif canPWK[0]:
            if not self.combat:
                outstr += 'Going to combat\n'
                self.goToCombat(verb)
            removed = 0
            for creature in self.creatures:
                if creature.name == 'SteamKin' and creature.counters == 3 and removed < canPWK[1]:
                    creature.counters = 0
                    self.mana += 3
                    removed += 1
                    outstr += 'Counters to cast {} (now {} mana)\n'.format(creature.name, self.mana)

        # Check if any of the light up the stage cards are castable
        elif any([c.canPlay(self) for c in self.lightCards]):
            for cloc in range(len(self.lightCards)):
                if self.lightCards[cloc].canPlay(self):
                    self.cast(self.lightCards[cloc])
                    outstr += '{} cast from exile with {} turns left (now {} mana)\n'.format(self.lightCards.pop(cloc), self.lightTimer.pop(cloc), self.mana) 
                    break

        # Check if any of the light up the stage cards are castable with steamkin, if so make mana
        elif max(canPLUWK) > 0:
            if not self.combat:
                outstr += 'Going to combat\n'
                self.goToCombat(verb)
            removed = 0
            for creature in self.creatures:
                if creature.name == 'SteamKin' and creature.counters == 3 and removed < max(canPLUWK):
                    creature.counters = 0
                    self.mana += 3
                    removed += 1
                    outstr += 'Counters to cast {} (now {} mana)\n'.format(creature.name, self.mana)

        # If not castable, break
        else:
            outstr += '{} on top, can\'t cast (now {} mana)\n'.format(self.library[0], self.mana)
            if verb:
                print(outstr)
            raise EndTurn 

    def instantCastLoop(self, libIndex, verb=0):
        outstr = ''
        # Check if there are cards left:
        if len(self.library) == 0:
            raise PassPriority
        # Check if castable with SteamKin counters now, save info
        canPWK = self.library[libIndex].canPlayWSteamKin(self, len([SK for SK in self.creatures if SK.name == 'SteamKin' and SK.counters == 3]))
        canPLUWK = [c.canPlayWSteamKin(self, len([SK for SK in self.creatures if SK.name == 'SteamKin' and SK.counters == 3]))[1] for c in self.lightCards]
        # If top isn't an instant, break
        if library[libIndex].type != 'instant':
            raise PassPriority
        
        # If castable, cast
        elif self.library[libIndex].canPlay(self):
            self.cast(self.library[libIndex])
            outstr += '{} cast (now {} mana)\n'.format(self.library.pop(libIndex), self.mana)

        # If castable with SteamKin counters make mana
        elif canPWK[0]:
            removed = 0
            for creature in self.creatures:
                if creature.name == 'SteamKin' and creature.counters == 3 and removed < canPWK[1]:
                    creature.counters = 0
                    self.mana += 3
                    removed += 1
                    outstr += 'Counters to cast {} (now {} mana)\n'.format(creature.name, self.mana)

        # If not castable, break
        else:
            outstr += '{} on top, can\'t cast (now {} mana)\n'.format(self.library[libIndex], self.mana)
            if verb:
                print(outstr)
            raise PassPriority

def singleSimFrenzy(turns, library, lands=4, creatures=0, verb = 1, lft=0):
    outL = []
    outstr = ''
    b = Boardstate(library, lands, creatures)
    b.lft = lft
    currentT = 0
    b.mana -= 4
    while currentT <= turns:
        # A lot of complexity here is for Light up the Stage and SteamKin
        # Limit to 100 game actions in a turn, breaks infinite loops and other bugs
        # Shouldn't be any problems left, but you never know
        currentGA = 0
        try:
            while currentGA<100:#True:
                currentGA += 1
                b.castLoop()   
        except EndTurn:
            pass

        # Have we gone to combat yet?
        if not b.combat:
            outstr += 'Going to combat\n'
            b.goToCombat(verb)
                
        # New turn
        outL.append(b.spectacle)
        b.lft = 0
        b.mana = b.lands
        b.combat = 0
        b.spectacle = 0
        b.lightCards = [c for c,t in zip(b.lightCards,b.lightTimer) if t-1>0]
        b.lightTimer = [t-1 for t in b.lightTimer if t-1>0]
        currentT += 1
        outstr += 'Turn {}, starting with {} mana\n'.format(currentT, b.mana)
        outstr += '{}\n'.format(len(b.library))
        try:
            b.instantCastLoop(0)
        except PassPriority:
            pass
        if len(library) != 0:
            outstr += '{} drawn for turn\n'.format(b.library.pop(0))
        if verb:
            print(outstr)
        for creature in b.creatures:
            creature.haste = 1

    return outL

verb = 0
maxItter = 10000
maxLand = 4
turns = 5
lft = 0 # land for turn
out = np.zeros((maxLand, maxItter, turns+1))

# Populate the decklist (last value is Qtty)
deckList = [Card('Firebrand', 1, 1, 1, 'creature', 0, 1, 1, 0, 4),
            Card('Lavarunner', 1, 1, 1, 'creature', 0, 2, 1, 1, 4),
            Card('Pyromancer', 2, 2, 2, 'creature', 2, 2, 0, 1, 4),
            Card('SteamKin', 2, 2, 2, 'creature', 0, 1, 0, 0, 4),
            Card('Chainwhirler', 3, 3, 3, 'creature', 1, 3, 0, 0, 4),
            Card('Shock', 1, 1, 3, 'instant', 2, 0, 0, 0, 4),
            Card('Strike', 2, 2, 3, 'instant', 3, 0, 0, 0, 4),
            Card('Skewer', 3, 1, 3, 'sorcery', 3, 0, 0, 0, 2),
            Card('LightUp', 3, 1, 3, 'sorcery', 0, 0, 0, 0, 4),
            Card('WizardL', 3, 3, 1, 'instant', 3, 0, 0, 0, 4),
            Card('Frenzy', 4, 4, 4, 'enchantment', 0, 0, 0, 0, 3),
            Card('Mountain', 0, 0, 0, 'land', 0, 0, 0, 0, 19)
            ]

for land in range(maxLand):
    for i in range(maxItter):
        library = []
        for card in deckList:
            for c in range(card.qtty):
                library.append(copy.deepcopy(card))
        shuffle(library)
        if i%100 == 0: # Give us some indication of how it's going.
            print('{}/{}, {}/{}'.format(i, maxItter, land+1, maxLand))
        out[land,i] = np.array(singleSimFrenzy(turns, library, lands=land+4, verb=verb, lft=lft))
        if verb:
            print('----------------------------------------------------------------------------')

# Indexed via
# [landCount][runNo][turnNo]
outA = np.array(out)

# Indexed via
# [landCount][turnNo][damage]
plotL = []
for land in range(maxLand):
    plotL.append([])
    for turn in range(turns):
        plotL[-1].append([len([d for d in outA[land,:,turn] if d == dcount]) for dcount in range(50)])

def distPlot(outA, maxLand = 4, turn = 4):
    for land in range(maxLand):
##        plt.plot(range(50), plotL[land][3], label = land)
        plt.hist(outA[land,:,turn], histtype='step',cumulative=-1, density=True, bins=range(50), label=land)
    plt.legend(loc='upper right')
    plt.xlabel('Damage')
    plt.ylabel('1 - Cumulative Probability')
    plt.title('Cumulative Distribution Function for 4 Lands, 4 Turns')
    plt.show()

def averagePlot(outA):
    # [landCount][turnNo]
    meanL = []
    for land in range(maxLand):
        meanL.append([])
        for turn in range(turns):
            meanL[-1].append(np.mean(outA[land,:,turn]))
    for land in range(4):
        plt.scatter(range(5), meanL[land], label='{} lands'.format(land+4))
    plt.title('Average Damage Dealt')
    plt.legend()
    plt.xlabel('Turn Number')
    plt.ylabel('Average Damage')
    plt.show()

def medianPlot(outA):
    # [landCount][turnNo]
    medianL = []
    for land in range(maxLand):
        medianL.append([])
        for turn in range(turns):
            medianL[-1].append(np.median(outA[land,:,turn]))
    for land in range(4):
        plt.scatter(range(5), medianL[land], label='{} lands'.format(land+4))
    plt.title('Median Damage Dealt')
    plt.legend()
    plt.xlabel('Turn Number')
    plt.ylabel('Average Damage')
    plt.show()

pickle.dump(outA, open('10kOutA.p', 'wb'))
