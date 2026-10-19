PLAN = [
 # 1 Swift opens at once
 [A(W, "strike", move="Quick Attack", part="Chest", flavor="Swift opens at once: a streak across the shelf straight into the big bird's chest")],
 # 2 Glacia rises and answers with ice from above
 [A(G, "strike", move="Ice Beam", part="Left Wing", reposition="take off", flavor="Glacia lifts off the shelf without hurry, turns in the air and lays a beam of white cold across the swallow's wing")],
 # 3 Swift takes off and dives
 [A(W, "strike", move="Aerial Ace", part="Upper Back", reposition="take off", flavor="Swift goes up in a corkscrew, gets above her and cuts down across her back")],
 # 4 Blizzard
 [A(G, "strike", move="Blizzard", hits=[{"part":"Head","severity":"heavy"},{"part":"Left Wing","severity":"heavy"},{"part":"Right Wing","severity":"solid"},{"part":"Chest","severity":"solid"}], flavor="she beats her wings once and the air between them fills with driving snow")],
 # 5 Steel Wing
 [A(W, "strike", move="Steel Wing", part="Left Wing", flavor="Swift comes out of the snow with her wing gone hard as steel and slashes it across the Articuno's left wing")],
 # 6 Glacia Air Slash
 [A(G, "strike", move="Air Slash", hits=[{"part":"Chest","severity":"solid"},{"part":"Tail","severity":"light"}], flavor="a blade of cold air flicked off her wingtip after the swallow")],
 # 7 Steel Wing again, on the wing she already hit
 [A(W, "strike", move="Steel Wing", part="Left Wing", flavor="Swift doubles back, wings flashing hard and grey, and rakes the Articuno's left wing as she passes")],
 # 8 Freeze-Dry
 [A(G, "strike", move="Freeze-Dry", hits=[{"part":"Right Wing","severity":"heavy"},{"part":"Chest","severity":"solid"}], flavor="a breath of cold so dry it smokes, laid along the swallow's right wing")],
 # 9 Brave Bird
 [A(W, "strike", move="Brave Bird", part="Chest", flavor="Swift folds her wings and throws her whole body at the Articuno's breast, wrapped in blue fire")],
 # 10 Hurricane brings her down
 [A(G, "strike", move="Hurricane", hits=[{"part":"Left Wing","severity":"heavy"},{"part":"Right Wing","severity":"heavy"},{"part":"Head","severity":"solid"}], launch="knocked down", landing=[{"surface":"the scree slope","parts":["Left Wing","Back"],"severity":"heavy"}], flavor="she turns the wind itself on the swallow and slams her out of the sky onto the scree")],
 # 11 Swift back up, dive
 [A(W, "strike", move="Aerial Ace", part="Head", reposition="take off", flavor="Swift is off the scree in a flash and cuts back down across the grounded Articuno's head")],
 # 12 Ice Shard
 [A(G, "strike", move="Ice Shard", part="Left Wing", flavor="without moving her feet she flicks a dart of ice up at the swallow's wing")],
 # 13 Steel Wing on the hurt wing
 [A(W, "strike", move="Steel Wing", part="Left Wing", flavor="Swift drops on her from above and brings a steel-hard wing down across the wing she has already hurt twice")],
 # 14 Glacia gathers herself
 [A(G, "breather", flavor="she stands on the shelf with her hurt wing held half open, breathing the cold in slowly, watching the swallow circle")],
 [A(W, "strike", move="Peck", part="Head", count=3, flavor="Swift hovers in her face and pecks, three fast jabs at the crown")],
 [A(G, "strike", move="Blizzard", flavor="the whole sky over the shelf goes white")],
 [A(W, "strike", move="Brave Bird", part="Left Wing", reposition="take off", flavor="Swift hauls herself into the air and throws everything she has left at the ruined wing")],
 [A(G, "strike", move="Ice Beam", part="Chest", flavor="a beam of white cold straight up into the swallow's breast")],
 [A(W, "strike", move="Aerial Ace", part="Neck", flavor="one more cut, low across the Articuno's neck")],
 [A(G, "strike", move="Freeze-Dry", hits=[{"part":"Right Wing","severity":"heavy"},{"part":"Forked Tail","severity":"solid"}], flavor="a breath of smoking cold over the swallow's good wing")],
 [A(W, "strike", move="Quick Attack", part="Head", flavor="a last streak straight at her head")],
 [A(G, "strike", move="Ice Shard", part="Chest", flavor="a dart of ice into the swallow's chest")],
 [A(W, "strike", move="Wing Attack", part="Left Wing", flavor="a beat of her wing across the ruined one")],
 [A(G, "strike", move="Ice Beam", part="Throat", flavor="the beam again, at her throat")],
 [A(W, "strike", move="Peck", part="Head", flavor="a jab at the crown")],
 [A(G, "strike", move="Air Slash", hits=[{"part":"Chest","severity":"heavy"}], flavor="a blade of air")],
]
