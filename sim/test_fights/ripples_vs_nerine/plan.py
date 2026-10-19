PLAN = [
 # 1 Nerine opens like a brawler: straight in
 [A(N, "strike", move="Quick Attack", part="Chest", flavor="no circling: she blurs straight in, shoulder-first, into the chest")],
 # 2 Ripples answers from range, patient
 [A(R, "strike", move="Water Gun", hits=[{"part":"Head","severity":"solid"},{"part":"Muzzle","severity":"solid"},{"part":"Chest","severity":"light"}], flavor="steps back and puts a jet of water in her face to keep her off")],
 # 3 Nerine walks through it and grabs
 [A(N, "grapple", part="Right Upper Arm", hits=[{"part":"Right Upper Arm","with":"her paws","severity":"light"}], flavor="ducks through the spray and clamps both paws on Ripples' arm"),
  A(N, "strike", move="Brick Break", part="Chest", count=3, flavor="short chopping paw blows into the chest at no distance")],
 # 4 Nerine throws her into the oak
 [A(N, "throw", landing=[{"surface":"an old oak","parts":["Upper Back","Lower Back","Head"],"severity":"heavy"},{"surface":"the root-knotted ground","parts":["Left Hip","Lower Back"],"severity":"solid"}], flavor="swings her round by the arm she holds and hurls her back-first into the old oak")],
 # 5 Ripples down, Nerine follows with a stomp/knee
 [A(N, "strike", move="improvised", improvised_name="dropping knee", improvised_type="Normal", part="Stomach", severity="heavy", flavor="drops a knee into her middle as she lies among the roots")],
 # 6 Ripples answers from the ground: Ice Fang on the leg near her
 [A(R, "strike", move="Ice Fang", part="Left Knee", flavor="from the ground, snaps freezing teeth onto the knee that's planted beside her")],
 # 7 Ripples gets up / breather
 [A(R, "breather", flavor="backs off a step, shakes her head clear and watches, letting Nerine come to her")],
 # 8 Ripples counters the rush with Aqua Jet into the pine
 [A(R, "strike", move="Aqua Jet", part="Chest", charge_into="a tall pine", flavor="as Nerine rushes in again Ripples meets her low in a sheath of water and drives her back into a pine")],
 # 9 Nerine gets up, furious
 [A(N, "breather", flavor="spits out lake water at the foot of the pine and claws her way up the bark, glaring")],
 # 9b Nerine, off the tree, grabs the scruff and bites the shoulder
 [A(N, "grapple", part="Neck", hits=[{"part":"Neck","with":"her paw","severity":"light"}], flavor="shoves off the trunk and gets a paw fisted in the scruff of Ripples' neck"),
  A(N, "strike", move="Bite", part="Left Shoulder", flavor="hauls her head down and bites the shoulder")],
 # 10 Nerine slams her down on her back onto the roots
 [A(N, "slam", landing=[{"surface":"the root-knotted ground","parts":["Upper Back","Lower Back","Head"],"severity":"brutal"}], flavor="lifts her by the scruff and the arm and drives her down back-first onto the roots")],
 # 11 Ripples, on her back, binds Nerine's leg with her tails
 [A(R, "hold_start", move="Tail Bind", part="Right Knee", hits=[{"part":"Right Knee","with":"her twin tails","severity":"firm"},{"part":"Right Thigh","with":"her twin tails","severity":"firm"}], ramp="tightening", flavor="from the ground she whips both tails round Nerine's right leg and wrenches")],
 # 12 Nerine stomps/chops at her while bound; Ripples keeps it on
 [A(N, "struggle", defender="", flavor="hops and yanks and chops at the tails")],
 [A(R, "strike", move="Water Gun", hits=[{"part":"Head","severity":"solid"},{"part":"Throat","severity":"solid"},{"part":"Chest","severity":"light"}], flavor="from the ground, a jet up into her face while the tails keep the leg")],
 # 15 Nerine barges her into the fallen trunk
 [A(N, "strike", move="improvised", improvised_name="shoulder barge", improvised_type="Normal", part="Chest", severity="heavy", charge_into="the fallen trunk", flavor="shakes the leg out and goes straight back in, shoulder down, and runs Ripples backward into the fallen trunk")],
 # 16 pummel her against it
 [A(N, "strike", move="Brick Break", part="Stomach", count=3, flavor="keeps her pressed to the moss with one forearm and chops at her middle")],
 # 17 Ripples answers with Crunch
 [A(R, "strike", move="Crunch", part="Left Forearm Fin", flavor="twists her head down and bites the forearm that's pinning her to the log")],
 # 18 Aqua Tail to the back
 [A(N, "strike", move="Aqua Tail", part="Upper Back", launch="knocked down", flavor="spins and whips both water-wrapped tails across her back as she turns away")],
 # 19 Nerine drags her by the tails across the sand into the boulder
 [A(N, "drag", landing=[{"surface":"the wet sand at the waterline","parts":["Upper Back","Lower Back"],"severity":"solid"},{"surface":"a boulder at the edge of the beach","parts":["Head","Left Shoulder"],"severity":"heavy"}], flavor="grabs both of Ripples' tails and hauls her on her back across the sand and into the boulder")],
 # 20 Ripples, desperate, throws her tails round Nerine's neck from the ground
 [A(R, "hold_start", move="Tail Bind", part="Neck", hits=[{"part":"Neck","with":"her twin tails","severity":"crushing"},{"part":"Throat","with":"her twin tails","severity":"firm"}], ramp="tightening", flavor="as Nerine bends over her, both tails whip up round her neck and cinch")],
 [A(N, "struggle", defender="", flavor="claws at the tails round her throat, staggering")],
 [A(N, "struggle", defender="", flavor="drops to a knee, still clawing, face darkening")],
 [A(N, "strike", move="Brick Break", part="Head", count=2, flavor="gives up on the tails and chops down at Ripples' head instead")],
 # 24 surge: Ripples bites the throat
 [A(R, "strike", move="Crunch", part="Throat", flavor="the surge hits and she lunges up under Nerine's chin and bites into the throat the tails just left")],
 # 25 Ice Fang onto the hurt arm
 [A(R, "strike", move="Ice Fang", part="Left Upper Arm", flavor="goes for the arm she bit before, teeth white with frost")],
 # 26 Nerine, furious, throws her back-first into the oak
 [A(N, "throw", landing=[{"surface":"an old oak","parts":["Upper Back","Lower Back"],"severity":"brutal"},{"surface":"the root-knotted ground","parts":["Stomach","Chest"],"severity":"solid"}], flavor="tears the arm free, grabs her round the middle and hurls her back-first into the old oak")],
 [A(N, "strike", move="Aqua Tail", part="Head", flavor="walks over and brings both water-wrapped tails down on her head")],
 [A(N, "strike", move="Brick Break", part="Head", flavor="a chop to the side of the head")],
 [A(N, "strike", move="Bite", part="Neck", flavor="a hard bite at the back of the neck")],
 [A(N, "strike", move="Quick Attack", part="Chest", flavor="a blur straight into her chest")],
 [A(N, "strike", move="Brick Break", part="Stomach", flavor="a chop into her middle")],
]
