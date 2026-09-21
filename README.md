# pfa-week02

Assignment Introduction and Preface

I chose "Path B" and wrote a completely new Python script.
In the previous version, I simply had Claude generate random objects whose size, color, and position could be adjusted via the GUI. For this assignment, I adopted a different approach: while I still wanted random object generation, I specified that whenever a sphere was generated, a cube had to be created immediately next to it. I then tested the feasibility of this code. I discovered that some of the randomly generated objects would overlap to varying degrees. Given the assignment requirement to include "undo" and "delete" functions, I implemented a system where overlapping objects are grouped together; if an overlap occurs, the group is deleted. I also included logic allowing the user to undo the last action if the number of objects in the Maya scene falls below a certain threshold. That is the general outline of my approach.
However, the code still has some issues—for instance, the number of generated objects consistently falls short of my target count, which is necessary for the undo function to be usable—so I still need to optimize and refine it.

## Demo Record:

 [Watch Assessment 2 Demo Vidoe]{https://youtu.be/cFJDHrJMSj8}
